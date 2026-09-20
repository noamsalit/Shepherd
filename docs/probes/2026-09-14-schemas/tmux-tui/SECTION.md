# Surface: interactive Claude Code (TUI) under tmux

All captures on this surface were made on 2026-09-14 with `claude --version` = `2.1.270 (Claude Code)` and `tmux 3.4`, Linux 6.8. Each capture folder has a `versions.txt`.

**Evidence folder:** `docs/probes/2026-09-14-schemas/tmux-tui/`

| Folder | Script (re-run from repo root) | What it covers |
|---|---|---|
| `run-20260914T154946Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` | trust dialog, hooks, idle/permission, send-keys, resize, /rename, /compact, fork, /exit, SIGTERM, kill-session |
| `supp-20260914T155346Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py` | `--name`/`--session-id` at spawn, `capture-pane -S -2000` on the alternate screen, `pipe-pane` |
| `supp2-20260914T155625Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp2.py` | prompt-suggestion ghost text plus a bare Enter; text typed into a permission dialog |
| `supp3-20260914T160052Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp3.py` | typing a message over ghost text |
| `headless-20260914T160308Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py` | the same scenarios with `claude -p`, for the parity table |

Helpers: `capture_hook.sh` is the hook command. It appends the raw stdin plus the event name, our UTC timestamp, the claude pid and the process ancestry. `make_settings.py` writes throwaway settings that register all 33 events, set `enabledPlugins: {"cc10x@cc10x": false}` and set `remoteControlAtStartup: false`. `field_matrix.py`, `count_events.py` and `analyze_fork.py` are the analysis scripts.

**Probe hygiene (applies to every block below).**
- Every tmux call passed `-L shepherd-probe`, and teardown was `tmux -L shepherd-probe kill-server`. Proof: `*/teardown.txt` says "no server running on /tmp/tmux-0/shepherd-probe".
- The tmux server was started under `env -i`, so the probe sessions did not inherit `$TMUX` or `CLAUDECODE`.
- cc10x hooks did not fire. The debug log shows `Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled)` and `Registered 0 hooks from 0 plugins` (`run-20260914T154946Z/debug-a.log`), and every hook captured from a TUI session has `_ancestry` `capture_hook.sh → sh → claude → tmux: server`. Headless captures (`headless-20260914T160308Z/hooks-h.jsonl`) show `capture_hook.sh → sh → claude → python3 → timeout → ...` instead.
- Privacy (audit): the machine's host name and `/etc/machine-id` value appear in some captures (`pane_title` before the TUI starts, sidecar `pidDomain`). They are host identifiers, not session content, and are shown as `<redacted: ...>` in the examples below.
- An exploratory run done before the scripted one left Remote Control at its default (on), and the sidecar then carried a `bridgeSessionId`. That run was discarded and is not cited. The scripted runs set `remoteControlAtStartup: false`, and no `bridgeSessionId` appears in their sidecars.
- Privacy: every example below comes from throwaway sessions in `/tmp/shp-tui-*` directories. None of the user's transcripts were read.

---

## Workspace-trust dialog (TUI, tmux capture-pane)

- **Produced by:** Claude Code 2.1.270, interactive mode, first launch in a directory that has no trust entry
- **Consumed by:** §9 LocalRunner spawn (D14), §8 `state = starting` rule (line 940), M3. It also affects every owned spawn into a new worktree (M5)
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` (steps 1, 1b). Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/01-trust-dialog.txt`)
```text
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:

 /tmp/shp-tui-A-4tvrx00n

 Quick safety check: Is this a project you created or one you trust? (Like your own code, a well-known open source project, or work from your team). If not,
 take a moment to review what's in this folder first.

 Claude Code'll be able to read, edit, and execute files here.

 Security guide

 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
```
ANSI form (`capture-pane -e -p` rendered through `cat -v`; full capture: `run-20260914T154946Z/01-trust-dialog.ansi.cat-v.txt`):
```text
^[[39m ^[[1m^[[38;5;220mAccessing^[[0m ^[[1m^[[38;5;220mworkspace:^[[0m
...
 ^[[38;5;246m^[]8;id=zaxmda;https://code.claude.com/docs/en/security^[\Security guide^[[39m^[]8;;^[\

 ^[[38;5;153mM-bM-^]M-/^[[39m ^[[38;5;153mNo,^[[39m ^[[38;5;153mexit^[[39m
   Yes, I trust this folder
```
Pane state while the dialog is shown (`run-20260914T154946Z/01-trust-dialog-fmt.txt`) and hook counts (`01-hooks-before-trust.txt`):
```text
alternate_on=0 pane_pid=4041880 pane_dead=0 pane_title=<redacted: host name> cursor=1,13
after >=15s on the trust dialog: hooks-a lines=0 (project settings), hooks-b lines=0 (--settings)
```
Refusing the dialog (Enter on the default) in `probe_b`, whose hooks came from `--settings` (`01b-list-sessions-after-refuse.txt`, `debug-b.log`):
```text
probe_b|4041912|1|1||0|160x45|
2026-09-14T15:50:07.444Z [DEBUG] Skipping SessionEnd:other hook execution - workspace trust not accepted
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| header line | text | always | `Accessing workspace:` | bold, SGR `38;5;220` |
| path line | text | always | the cwd | bold |
| question | text | always | `Quick safety check: Is this a project you created or one you trust?...` | a stable substring to detect the dialog |
| option 1 | text | always | `No, exit` | **selected by default** (`❯`) |
| option 2 | text | always | `Yes, I trust this folder` | reached with `Down` |
| footer | text | always | `Enter to confirm · Esc to cancel` | |
| `#{alternate_on}` | 0/1 | always | `0` while the dialog is shown, `1` once the TUI starts | usable as a detector |
| `#{pane_title}` | string | always | the host name while the dialog is shown, then `✳ Claude Code` | see the tmux formats block |
| sidecar `~/.claude/sessions/<pid>.json` | file | never observed during the dialog | `<absent: ...>` | `01-trust-dialog-sidecar.json` |

**Variants and edge cases:**
- Accepting takes `send-keys Down` then `send-keys Enter`. Output: `01c-trust-yes-selected.txt` shows `❯ Yes, I trust this folder`. `SessionStart` (`source: startup`) then fired (`hooks-a.jsonl` line 1).
- A bare Enter picks "No, exit". The process exits with **status 1** (`pane_dead_status` = 1).
- No hook fires before trust is accepted. This held for hooks in project `.claude/settings.json` (dirA) and for hooks passed with `--settings` (dirB): 0 lines each after at least 15 s. On refusal Claude Code logs that it skipped `SessionEnd:other` hook execution, so a refused spawn emits no hook at all.
- Once accepted, trust persists. Later spawns into the same directory (`probe_fork`, `probe_sig`) showed no dialog.
- `claude -p` in a fresh untrusted directory did not stop on a dialog, and hooks fired (`headless-20260914T160308Z/event-sequence.txt`).
- Not verified: what `Esc` does on this dialog.

**Spec alignment:**
- Spec line 940 says `starting` holds "until the first signal of any kind arrives, or `SPAWN_TIMEOUT_S` (60) elapses → then `stopped` / `crashed`". In reality an owned TUI spawn into an untrusted directory sends **no hook and writes no sidecar** until a human answers (observed for at least 15 s; the full 60 s was not waited out). It does draw the dialog on the pty. Line 939 counts "pty output" as a `running` signal, so depending on how "signal of any kind" is read, the session is mislabelled either `running` (because of the dialog's pty output) or `stopped`/`crashed` after 60 s. It is never recognised as blocked on a human. A runner that sends a bare Enter exits the process with status 1. Evidence: `run-20260914T154946Z/01-hooks-before-trust.txt` and `01b-list-sessions-after-refuse.txt`.
- §9 (lines 1131–1145) and §18 (line 2325) never mention the trust dialog. The detector has to be pane text plus `alternate_on=0`, not a hook. (evidence as above)

---

## Hook event parity: interactive TUI versus headless `-p`

- **Produced by:** Claude Code 2.1.270. The TUI ran in tmux 3.4; headless used `claude -p --output-format json`.
- **Consumed by:** §8 event table (lines 877–889), the needs-you/stop rules (lines 935–970), §9 mailbox trigger (line 1181), D12, D24, M1 (hookd), M3 (owned sessions)
- **Probe:** `probe_tui.py` + `probe_headless_parity.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py && python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py`
- **Status:** partially verified. The scenarios in the table were verified live 2026-09-14; the many events that were registered but never provoked are listed under "not verified".

**Real example** (TUI event sequence for one session; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a-event-sequence.txt`)
```text
2026-09-14T15:50:12.998Z 71757dd1 SessionStart startup
2026-09-14T15:50:16.536Z 71757dd1 UserPromptSubmit 
2026-09-14T15:50:17.936Z 71757dd1 MessageDisplay 
2026-09-14T15:50:17.949Z 71757dd1 Stop 
2026-09-14T15:50:21.495Z 71757dd1 SubagentStop 
2026-09-14T15:51:17.976Z 71757dd1 Notification idle_prompt
2026-09-14T15:51:20.122Z 71757dd1 UserPromptSubmit 
2026-09-14T15:51:21.462Z 71757dd1 MessageDisplay 
2026-09-14T15:51:21.468Z 71757dd1 Stop 
2026-09-14T15:51:23.681Z 71757dd1 UserPromptSubmit 
2026-09-14T15:51:25.466Z 71757dd1 PreToolUse 
2026-09-14T15:51:25.526Z 71757dd1 PermissionRequest 
2026-09-14T15:51:31.548Z 71757dd1 Notification permission_prompt
2026-09-14T15:51:31.789Z 71757dd1 PostToolUse 
2026-09-14T15:51:31.801Z 71757dd1 PostToolBatch 
2026-09-14T15:51:33.535Z 71757dd1 MessageDisplay 
2026-09-14T15:51:33.561Z 71757dd1 Stop 
2026-09-14T15:51:34.747Z 71757dd1 UserPromptSubmit 
2026-09-14T15:51:38.746Z 71757dd1 PreToolUse 
2026-09-14T15:51:41.247Z 71757dd1 UserPromptSubmit 
2026-09-14T15:51:50.815Z 71757dd1 PostToolUse 
2026-09-14T15:51:50.834Z 71757dd1 PostToolBatch 
2026-09-14T15:51:53.806Z 71757dd1 MessageDisplay 
2026-09-14T15:51:53.811Z 71757dd1 Stop 
2026-09-14T15:52:00.594Z 71757dd1 SubagentStop 
2026-09-14T15:52:51.987Z 71757dd1 PreCompact manual
2026-09-14T15:53:06.477Z 71757dd1 SubagentStop 
2026-09-14T15:53:06.512Z 71757dd1 SessionStart compact
2026-09-14T15:53:06.523Z 71757dd1 PostCompact manual
...
2026-09-14T15:53:33.685Z 71757dd1 SessionEnd other
```
Headless counterpart (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/event-sequence.txt`):
```text
== h1_pong
  2026-09-14T16:03:08.588Z 55b21a24 SessionStart startup 
  2026-09-14T16:03:09.459Z 55b21a24 UserPromptSubmit  
  2026-09-14T16:03:10.522Z 55b21a24 MessageDisplay  
  2026-09-14T16:03:10.582Z 55b21a24 Stop  
  2026-09-14T16:03:10.612Z 55b21a24 SessionEnd other 
== h2_permission_default_mode
  2026-09-14T16:03:11.893Z 55b21a24 SessionStart resume 
  2026-09-14T16:03:12.347Z 55b21a24 UserPromptSubmit  
  2026-09-14T16:03:14.061Z 55b21a24 PreToolUse Bash 
  2026-09-14T16:03:14.092Z 55b21a24 PermissionRequest Bash 
  2026-09-14T16:03:14.111Z 55b21a24 PostToolBatch  
  2026-09-14T16:03:17.656Z 55b21a24 MessageDisplay  
  2026-09-14T16:03:17.724Z 55b21a24 Stop  
...
```

| Scenario | TUI (tmux) events | Headless `-p` events | Notes |
|---|---|---|---|
| launch | `SessionStart{source:startup}` only after trust | `SessionStart{startup}` | TUI: no hooks before trust |
| prompt → answer | `UserPromptSubmit`, `MessageDisplay`, `Stop`, then `SubagentStop{agent_type:""}` 3–7 s later | `UserPromptSubmit`, `MessageDisplay`, `Stop`, `SessionEnd{other}` | the trailing `SubagentStop` is TUI-only, with no `SubagentStart` (prompt-suggestion helper) |
| idle at prompt | `Notification{idle_prompt}` **60.03 s** after `Stop` (`04-idle-delay.txt`) | none (process exits) | one per idle period observed |
| tool needs permission | `PreToolUse`, `PermissionRequest`, then `Notification{permission_prompt}` **6.02 s** later if still unanswered (`06-permission-delay.txt`); after approval `PostToolUse`, `PostToolBatch` | `PreToolUse`, `PermissionRequest`, `PostToolBatch`; the call is auto-denied and listed in stdout `permission_denials` | no `PermissionDenied` or `PostToolUseFailure` in headless |
| permission answered < 6 s | `PermissionRequest` then `PostToolUse`, **no Notification** (4 prompts, `event-counts.txt`) | n/a | |
| message typed while running | `UserPromptSubmit` fires **immediately**, mid-turn, carrying the running turn's `prompt_id`; still **one** `Stop` | n/a | see the send-keys block |
| `/compact` | `PreCompact{manual}`, `SubagentStop`, `SessionStart{compact}`, `PostCompact{manual}` | `SessionStart{resume}`, `PreCompact{manual}`, `SubagentStop`, `SessionStart{compact}`, `PostCompact{manual}`, `SessionEnd{other}` | same order; `SessionStart{compact}` comes before `PostCompact` |
| `/rename` | **no hook** (`10-rename-hooks.txt`: `[]`) | `SessionStart{resume}`, `SessionEnd{other}` | the title shows up later as `session_title` |
| fork | `SessionStart{source:fork}` with a new `session_id` | same | |
| `/exit` | `SessionEnd{reason:prompt_input_exit}` | n/a (`-p` ends with `other`) | |
| tmux `kill-session` | `SessionEnd{reason:other}` 24 ms after the kill | n/a | fired even though the pty disappeared |
| `kill -TERM <claude pid>` | `SessionEnd{reason:other}`, `pane_dead_status` 143 | n/a | |

**Variants and edge cases:**
- `SubagentStop` arrived with no matching `SubagentStart` 10 times across 4 TUI captures, and `SubagentStart` arrived 0 times (`event-counts.txt`). `agent_type` was `""` and `last_assistant_message` was `"(silence)"` or the compact summary. These come from Claude Code's internal helpers: prompt suggestion and the compaction summarizer.
- `MessageDisplay` streams: 12 events about 100 ms apart for one 80-line reply (`supp-20260914T155346Z/05-hook-sequence.txt`).
- In the TUI, `/compact` prints each hook's command line with "completed successfully" into the pane (`run-20260914T154946Z/11-compact-after.txt`). That is pane noise, not hook data.
- No payload in any capture had an `effort` key (`event-counts.txt`, `field-matrix-a-and-supp.txt`).
- Not verified (not provoked on this surface): `StopFailure`, `PostToolUseFailure`, `PermissionDenied`, `Elicitation*`, `SubagentStart`, `TaskCreated`/`TaskCompleted`, `FileChanged`, `CwdChanged`, `Pre/PostModelSwitch`, `ConfigChange`, `InstructionsLoaded`, `Worktree*`, `TeammateIdle`, `Setup`, `DirectoryAdded`, `UserPromptExpansion`, `PreCompact{auto}`, `SessionEnd{clear|logout|resume}`. All 33 were registered. Only the events in the table fired.

**Spec alignment:**
- Spec line 885 maps `SubagentStart` / `SubagentStop` to `active_subagents`. In the TUI, `SubagentStop` fires after most turns and after `/compact` with no `SubagentStart`, so a counter goes negative (`event-counts.txt`, `field-matrix-a-and-supp.txt`).
- Spec line 937 counts `idle_prompt` as `needs_you` and "`needs_you` outranks `stopped`". Every idle TUI session therefore flips from `stopped` to `needs_you` 60.03 s after `Stop` (`run-20260914T154946Z/04-idle-delay.txt`; seen again in `supp2`). This follows the spec's rule literally, but the spec names neither the delay nor the consequence: every finished interactive session ends up in the Needs-You rail after a minute.
- Spec line 883 uses `Notification` / `PermissionRequest` for `needs_you`. `PermissionRequest` is the only prompt signal when the human answers within about 6 s. `permission_prompt` is delayed 6 s and sometimes never comes (`event-counts.txt`).
- Spec line 937 needs "an unresolved `PermissionRequest`". No explicit resolution event was observed on approval, and `PermissionRequest` has **no `tool_use_id`** (the preceding `PreToolUse` and the following `PostToolUse` do). Resolution on approval must be inferred from the next `PostToolUse` with the same `prompt_id` and `tool_name` (`run-20260914T154946Z/hooks-a.jsonl` lines 11–14). Denial ("3. No") was never chosen, so whether `PermissionDenied` marks that case is not verified.
- Spec line 929 lists `prompt_id`, `permission_mode` and `effort.level` as common fields. `permission_mode` is absent from `SessionStart`, `Notification`, `Pre/PostCompact`, `SessionEnd` and `MessageDisplay`; `effort` appears nowhere; `prompt_id` is absent from `SessionStart{startup|fork}` and from a `SessionEnd` with no prior prompt (`run-20260914T154946Z/field-matrix-a-and-supp.txt`, `hooks-a.jsonl` lines 1, 30, 36). Every TUI payload carries `scratchpad_dir`, which the spec does not list; headless `-p` payloads (`headless-20260914T160308Z/hooks-h.jsonl`) carry none.
- Spec lines 967–970 use `SessionEnd.end_reason`; the key is `reason` (`field-matrix-a-and-supp.txt`). Spec lines 962–963 use `Stop.stop_reason`; none of the 13 `Stop` payloads in the four TUI captures has that key (keys observed: `background_tasks`, `last_assistant_message`, `session_crons`, `stop_hook_active`). All were ordinary end-of-turn stops, though; the `tool_use`/`max_tokens` cases were not provoked, so this is "not observed", not a proven absence.
- Spec lines 964–965 (`crashed` / `killed`). The SIGTERM'd session (`probe_sig`, never prompted) emitted `SessionStart` then `SessionEnd{other}` and exited 143 with **no** `Stop`, so it matches the literal `crashed` rule. The spec's `killed` row (from `action_log`) covers it only if `killed` is evaluated before `crashed`, and the spec does not state that order. `kill-session` also emits `SessionEnd{other}`, and `other` has no row in the stop-reason table (`run-20260914T154946Z/14-hooks-after-sigterm.txt`, `15-hooks-after-kill.txt`).
- Spec line 1181 (mailbox triggers on `Stop`): aligned. `Stop` fires in the TUI at the end of every turn, including a turn that absorbed a mid-turn message.

---

## Notification payload (TUI: idle_prompt, permission_prompt)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 883, 937, 945–947; Needs-You rail §12; M1 (ingest), M2 (rail)
- **Probe:** `probe_tui.py` steps 3 and 4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** partially verified. The payload was verified live 2026-09-14 for `idle_prompt` and `permission_prompt` only; the other `notification_type` values the spec relies on (line 937: `agent_needs_input`, `elicitation_dialog`, `elicitation_url_dialog`; line 957: the `quota_auto_resume_*` values) were not provoked.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 6 and 13)
```json
{"_event":"Notification","_captured_at":"2026-09-14T15:51:17.976Z","_epoch":1789401077.976117,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042144,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"43ccd20b-51ee-4656-913f-3b0c4479a046","hook_event_name":"Notification","message":"Claude is waiting for your input","notification_type":"idle_prompt"}}
{"_event":"Notification","_captured_at":"2026-09-14T15:51:31.548Z","_epoch":1789401091.548040,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042190,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"23e44d08-6acd-4f45-b02c-a41d31833b17","hook_event_name":"Notification","message":"Claude needs your permission","notification_type":"permission_prompt"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | string (uuid) | always | | |
| `transcript_path` | string | always | `/root/.claude/projects/<slug>/<session_id>.jsonl` | the file may not exist yet |
| `cwd` | string | always | | |
| `scratchpad_dir` | string | always | `/tmp/claude-0/<slug>/<session_id>/scratchpad` | not in spec |
| `prompt_id` | string (uuid) | always | the last turn's prompt id | |
| `hook_event_name` | string | always | `Notification` | |
| `message` | string | always | `Claude is waiting for your input`, `Claude needs your permission` | generic: names no tool |
| `notification_type` | string | always | `idle_prompt`, `permission_prompt` | |
| `permission_mode` | string | never observed | | |

**Variants and edge cases:**
- `idle_prompt`: 60.027 s after `Stop` (`04-idle-delay.txt`). A second one was seen in `supp2` 60 s after a later `Stop`.
- `permission_prompt`: 6.021 s after `PermissionRequest`, and only if still unanswered (see the parity block).
- The `message` for a permission never names the tool. `needs_you_reason` has to come from `PermissionRequest.tool_name`/`tool_input`.

**Spec alignment:**
- Spec lines 945–947 say the UI shows *"needs permission: Bash(git push)"*. This is a clarification, not a contradiction: the `Notification` payload carries no tool, so the tool text must come from `PermissionRequest.tool_name`/`tool_input` (spec line 883 already lists `PermissionRequest` as a `needs_you_reason` source). When the human answers within about 6 s, `PermissionRequest` is the only prompt event (`run-20260914T154946Z/hooks-a.jsonl` lines 12–13).
- Otherwise aligned for `notification_type` values `idle_prompt` and `permission_prompt`.

---

## PermissionRequest payload (TUI, waiting for a human)

- **Produced by:** Claude Code 2.1.270, interactive, `permission_mode: default`
- **Consumed by:** §8 lines 883, 937; §11 line 1684; M1, M3
- **Probe:** `probe_tui.py` step 4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` line 12)
```json
{"_event":"PermissionRequest","_captured_at":"2026-09-14T15:51:25.526Z","_epoch":1789401085.526870,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042177,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"23e44d08-6acd-4f45-b02c-a41d31833b17","permission_mode":"default","hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"touch perm-probe.txt","description":"Create an empty file named perm-probe.txt"},"permission_suggestions":[{"type":"addDirectories","directories":["/tmp/shp-tui-A-4tvrx00n"],"destination":"session"},{"type":"setMode","mode":"acceptEdits","destination":"session"}]}}
```
What the pane shows at the same moment (`run-20260914T154946Z/06-permission-dialog.txt`):
```text
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Bash command

   touch perm-probe.txt
   Create an empty file named perm-probe.txt

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project
   3. No

 Esc to cancel · Tab to amend
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id`, `transcript_path`, `cwd`, `scratchpad_dir` | string | always | | |
| `prompt_id` | string | always | same as the turn's `UserPromptSubmit` | the only join key back to the turn |
| `permission_mode` | string | always | `default` | |
| `hook_event_name` | string | always | `PermissionRequest` | |
| `tool_name` | string | always | `Bash` | |
| `tool_input` | object | always | `{"command","description"}` | |
| `permission_suggestions` | array | always | `[{type:addDirectories,...},{type:setMode,mode:acceptEdits,...}]` | |
| `tool_use_id` | string | **never observed** | | present on the preceding `PreToolUse` (line 11) |

**Variants and edge cases:**
- The sidecar changes to `"status":"waiting","waitingFor":"permission prompt"` 14 ms after the hook (`06-sidecar-permission.json`).
- The default dialog option is `1. Yes`, so a bare Enter approves the call (see the send-keys block).
- Headless `-p`: the same event fires, then the call is auto-denied (`headless-20260914T160308Z/h2_permission_default_mode.stdout.json`, key `permission_denials`).

**Spec alignment:**
- Aligned that the event fires while waiting.
- Mismatch with the "unresolved `PermissionRequest`" rule (line 937): the payload has no `tool_use_id`, and nothing marks resolution (`run-20260914T154946Z/hooks-a.jsonl` lines 11–14).

---

## SessionEnd payload (TUI: /exit, tmux kill-session, SIGTERM)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 887, 938, 964–970; M2 stop reasons; M3 kill/interrupt
- **Probe:** `probe_tui.py` steps 11–13. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** partially verified. Reasons `prompt_input_exit` and `other` were verified live 2026-09-14; `clear`, `logout` and `resume` (spec lines 968–970) were not exercised.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 34, 36, 37)
```json
{"_event":"SessionEnd","_captured_at":"2026-09-14T15:53:21.156Z","_epoch":1789401201.156579,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042522,"_claude_pid":4042432,"_ancestry":[...],"payload":{"session_id":"c3f63742-5ff5-44ea-8f6e-a26d027b51d0","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/c3f63742-5ff5-44ea-8f6e-a26d027b51d0.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/c3f63742-5ff5-44ea-8f6e-a26d027b51d0/scratchpad","prompt_id":"2884fd06-a58c-4a40-bfbb-2e559736414e","hook_event_name":"SessionEnd","reason":"prompt_input_exit"}}
{"_event":"SessionEnd","_captured_at":"2026-09-14T15:53:28.700Z","_epoch":1789401208.700236,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042593,"_claude_pid":4042531,"_ancestry":[...],"payload":{"session_id":"f69f6919-4b86-4372-bf8e-41b85c596df0","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/f69f6919-4b86-4372-bf8e-41b85c596df0.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/f69f6919-4b86-4372-bf8e-41b85c596df0/scratchpad","hook_event_name":"SessionEnd","reason":"other"}}
{"_event":"SessionEnd","_captured_at":"2026-09-14T15:53:33.685Z","_epoch":1789401213.685183,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042606,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"SessionEnd","reason":"other"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id`, `transcript_path`, `cwd`, `scratchpad_dir` | string | always | | |
| `prompt_id` | string | sometimes (3/4) | | absent when no prompt was ever sent (SIGTERM right after launch) |
| `hook_event_name` | string | always | `SessionEnd` | |
| `reason` | string | always | `prompt_input_exit` (/exit), `other` (kill-session, SIGTERM; also every `-p` exit) | |
| `end_reason` | | never observed | | |

**Variants and edge cases:**
- `/exit`: pane dead with status 0. The pane then prints `Resume this session with:` / `claude --resume "<title>"` (`13-dead-pane.txt`). The sidecar file is removed (`13-fork-sidecar-after-exit.json`: absent).
- `kill-session`: the hook ran 24 ms after the kill command, even though the pty was gone. The claude pid and sidecar were gone within 6 s (`15-pid-after-kill.txt`).
- SIGTERM: `SessionEnd{other}`, then `pane_dead_status` 143 and an empty `pane_dead_signal` (`14-list-sessions-after-sigterm.txt`).
- The capture script is fork-free bash. A slower hook (python) was not tried here, so whether a slow `SessionEnd` hook survives `kill-session` is **not verified**.

**Spec alignment:**
- Spec lines 967–970 say `SessionEnd.end_reason`; reality is `reason`.
- `other` (kill, signal, `-p` exit) has no stop-reason row. Evidence: `run-20260914T154946Z/field-matrix-a-and-supp.txt`, `15-hooks-after-kill.txt`.

---

## SessionStart payload (TUI: startup, compact, fork, named spawn)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 881, 925–927; §9 `ask()` lines 1203–1205 (D13); §7 `engine_session_id` (line 652); §7.1 title (D29); M1, M3
- **Probe:** `probe_tui.py` (steps 1, 9, 10) and `probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
- **Status:** partially verified. Sources `startup`, `compact` and `fork` were verified live 2026-09-14 in the TUI; `resume` was seen only headless, and `clear` was not seen at all.

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 1, 28, 30; `supp-20260914T155346Z/hooks-s.jsonl` line 1)
```json
{"_event":"SessionStart","_captured_at":"2026-09-14T15:50:12.998Z","_epoch":1789401012.998584,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4041990,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","hook_event_name":"SessionStart","source":"startup","model":"claude-haiku-4-5-20251001"}}
{"_event":"SessionStart","_captured_at":"2026-09-14T15:53:06.512Z","_epoch":1789401186.512250,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042420,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"SessionStart","source":"compact","model":"claude-haiku-4-5-20251001","session_title":"shp-probe-title-1"}}
{"_event":"SessionStart","_captured_at":"2026-09-14T15:53:10.960Z","_epoch":1789401190.960490,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042467,"_claude_pid":4042432,"_ancestry":[...],"payload":{"session_id":"c3f63742-5ff5-44ea-8f6e-a26d027b51d0","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/c3f63742-5ff5-44ea-8f6e-a26d027b51d0.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/c3f63742-5ff5-44ea-8f6e-a26d027b51d0/scratchpad","hook_event_name":"SessionStart","source":"fork","session_title":"shp-probe-title-1","seconds_since_last_response":77,"context_tokens":2353,"prompt_cache_likely_expired":true,"estimated_cache_write_usd":0.0047}}
{"_event":"SessionStart","_captured_at":"2026-09-14T15:53:54.011Z","_epoch":1789401234.011437,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042688,"_claude_pid":4042647,"_ancestry":[...],"payload":{"session_id":"17b1da21-4505-43ae-8958-35764a620384","transcript_path":"/root/.claude/projects/-tmp-shp-tui-S-0omgx4oc/17b1da21-4505-43ae-8958-35764a620384.jsonl","cwd":"/tmp/shp-tui-S-0omgx4oc","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-S-0omgx4oc/17b1da21-4505-43ae-8958-35764a620384/scratchpad","hook_event_name":"SessionStart","source":"startup","model":"claude-haiku-4-5-20251001","session_title":"shp-spawn-name"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | string | always | with `--session-id <uuid>` it equals the requested uuid (`supp-.../02-sessionstart-and-sidecar.txt`) | lets the runner know `engine_session_id` before spawn |
| `transcript_path` | string | always | | the file does **not** exist yet at startup or fork; it is created on the first prompt |
| `cwd`, `scratchpad_dir` | string | always | | |
| `hook_event_name` | string | always | `SessionStart` | |
| `source` | string | always | `startup`, `compact`, `fork` (TUI); `resume` (headless) | |
| `model` | string | sometimes (4/5) | `claude-haiku-4-5-20251001` | absent on `fork` |
| `prompt_id` | string | sometimes (1/5) | | only on `compact` |
| `session_title` | string | sometimes (3/5) | `shp-probe-title-1`, `shp-spawn-name` | present once a user title exists (`/rename`, `--name`, or inherited by a fork) |
| `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd` | int/int/bool/float | sometimes (1/5) | `77`, `2353`, `true`, `0.0047` | fork only |
| `permission_mode` | | never observed | | |
| `start_reason` | | never observed | | |

**Variants and edge cases:**
- When the original had a user title, the fork inherited it (`hooks-a.jsonl` line 30). Every fork in the captures (TUI and headless h5) was of a session that already had a user title, so a fork of an untitled session was not observed.
- `SessionStart{compact}` keeps the same `session_id`.

**Spec alignment:**
- Spec line 1204–1205 says "the `SessionStart` hook's `start_reason` enum includes `fork`". The field is `source`, value `fork` (`run-20260914T154946Z/hooks-a.jsonl` line 30).
- Spec line 652 says `engine_session_id` is "Null until the engine emits it". This is an opportunity, not a contradiction: the rule stays correct for `attached` sessions, but for owned TUI spawns `--session-id <uuid>` makes the id known before the process starts, and `SessionStart` echoes it (`supp-20260914T155346Z/02-sessionstart-and-sidecar.txt`). The transcript file does not exist until the first prompt.

---

## PreCompact / PostCompact payload (manual /compact typed into the TUI)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 line 921 (context), line 966 (`context_exhausted`); M2
- **Probe:** `probe_tui.py` step 9. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** partially verified. `trigger: manual` was verified live 2026-09-14; `trigger: auto` and the `context_exhausted` case were not provoked.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 26, 29)
```json
{"_event":"PreCompact","_captured_at":"2026-09-14T15:52:51.987Z","_epoch":1789401171.987317,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042393,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"PreCompact","trigger":"manual","custom_instructions":null}}
{"_event":"PostCompact","_captured_at":"2026-09-14T15:53:06.523Z","_epoch":1789401186.523713,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042422,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"PostCompact","trigger":"manual","compact_summary":"<analysis>\nThis conversation is relatively brief and consists primarily of testing interactions. Let me analyze chronologically:\n\n1...
```
Order (`run-20260914T154946Z/11-compact-hook-order.txt`):
```text
2026-09-14T15:52:51.987Z PreCompact manual
2026-09-14T15:53:06.477Z SubagentStop 
2026-09-14T15:53:06.512Z SessionStart compact
2026-09-14T15:53:06.523Z PostCompact manual
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `trigger` | string | always | `manual` | |
| `custom_instructions` | null | always (PreCompact) | `null` | |
| `compact_summary` | string | always (PostCompact) | 4168 chars, starts `<analysis>` | model-written; treat as untrusted content |
| `prompt_id` | string | always | | |
| `permission_mode` | | never observed | | |

**Variants and edge cases:**
- The transcript gains a `system/compact_boundary` entry with `compactMetadata.trigger`, `preTokens`, `postTokens` and `durationMs` (`run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`, last line).
- Not verified: `trigger: auto`, and `PreCompact{auto}` without `PostCompact`. That would need a context-filling session.

**Spec alignment:** aligned for the manual path (the event pair exists and fires in the TUI). `context_exhausted` (line 966) is not verified.

---

## UserPromptSubmit from tmux send-keys

- **Produced by:** Claude Code 2.1.270, interactive, input delivered by `tmux -L shepherd-probe send-keys -t =<name>: -l '<text>'` then `send-keys ... Enter`
- **Consumed by:** §8 line 882 (`brief`); §9 write policy lines 1163–1177; mailbox lines 1179–1185 (D12); M3
- **Probe:** `probe_tui.py` steps 2, 3b, 5; `probe_tui_supp3.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 7, 19, 20; `supp-20260914T155346Z/hooks-s.jsonl` line 2)
```json
{"_event":"UserPromptSubmit","_captured_at":"2026-09-14T15:51:20.122Z","_epoch":1789401080.122869,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042157,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"b3fa1c2b-04f9-4a7e-9927-79bd34c8a4b1","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Reply with only the word MULTI.\n- note one\n- note two"}}
{"_event":"PreToolUse","_captured_at":"2026-09-14T15:51:38.746Z","_epoch":1789401098.746586,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042249,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchp...
{"_event":"UserPromptSubmit","_captured_at":"2026-09-14T15:51:41.247Z","_epoch":1789401101.247491,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042263,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"5c97d8c9-95d1-4808-90ae-756cfa656845","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Reply with only the word SECOND"}}
{"_event":"UserPromptSubmit","_captured_at":"2026-09-14T15:53:57.591Z","_epoch":1789401237.591180,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042744,"_claude_pid":4042647,"_ancestry":[...],"payload":{"session_id":"17b1da21-4505-43ae-8958-35764a620384","transcript_path":"/root/.claude/projects/-tmp-shp-tui-S-0omgx4oc/17b1da21-4505-43ae-8958-35764a620384.jsonl","cwd":"/tmp/shp-tui-S-0omgx4oc","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-S-0omgx4oc/17b1da21-4505-43ae-8958-35764a620384/scratchpad","prompt_id":"6f5b7ddd-b2b9-43da-a9ec-1905b3d64d82","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Print the integers from 1 to 80, one per line, nothing else.","session_title":"shp-spawn-name"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `prompt` | string | always | exactly the `send-keys -l` text; newlines kept as `\n` | a multi-line message is one prompt |
| `prompt_id` | string | always | a new id per idle-prompt submit; the **running turn's id** for a mid-turn submit | lines 18–20 share `5c97d8c9-...` |
| `permission_mode` | string | always | `default` | |
| `session_title` | string | sometimes (2/7) | `shp-probe-title-1`, `shp-spawn-name` | present when a user title exists |
| `source` | string | never observed | | |

**Variants and edge cases:**
- **Multi-line:** `send-keys -l "…\n- note one\n- note two"` did not submit early. All three lines sat in the input box until Enter (`05-multiline-typed.txt`, `05-multiline-hooks-before-enter.txt` = `[]`).
- **Mid-turn:** text sent while a tool ran made the pane show the queued text plus `❯ Press up to edit queued messages` (`07-running-after-send.txt`). `UserPromptSubmit` fired within 41 ms. The message was absorbed into the running turn at the next tool result: the model never produced `DONE-ONE`, answered `SECOND`, and there was one `Stop` (`07-stop-count.txt`).
- **Ghost text:** typing over a prompt-suggestion ghost replaced it. The submitted prompt was exactly the typed text (`supp3-20260914T160052Z/A3-hooks-after-enter.json`).

**Spec alignment:**
- Spec line 115 (D12 reasoning) says "Direct injection into a running session corrupts its state". In reality Claude Code has its own input queue: a mid-turn write is enqueued, then `absorbed_mid_turn` into the running turn. The running turn's instructions are silently merged with the new message, and there is no separate `Stop` per message. The mailbox design (line 1169, deliver at next `Stop`) stays correct; the stated failure mode is different from what happens (`run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`, `07-stop-count.txt`).
- Spec line 882 (`brief` from `UserPromptSubmit`): aligned. Note that a mid-turn message also arrives as `UserPromptSubmit`, so "first `UserPromptSubmit`" is the only safe brief.

---

## tmux send-keys delivery hazards (programmatic write path)

- **Produced by:** tmux 3.4 `send-keys` into Claude Code 2.1.270 TUI screens
- **Consumed by:** §9 write policy table lines 1165–1169; §9.5 `send_to_session` line 1229; D12, D40; M3
- **Probe:** `probe_tui_supp2.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp2.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/supp2-20260914T155625Z/B2-after-typing-into-dialog.txt`, after `send-keys -l "Reply with only the word NOPE"` into a permission dialog)
```text
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Bash command

   touch dialog-probe.txt
   Create an empty file named dialog-probe.txt

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to /tmp/shp-tui-X-7r0510pt from this project
   3. No

 Esc to cancel · Tab to amend
```
Then `send-keys Enter` (`supp2-20260914T155625Z/B-hooks.json`, `B-file-created.txt`):
```text
...
 [
  "2026-09-14T15:58:46.058Z",
  "PreToolUse",
  "Bash"
 ],
 [
  "2026-09-14T15:58:46.113Z",
  "PermissionRequest",
  "Bash"
 ],
 [
  "2026-09-14T15:58:48.537Z",
  "PostToolUse",
  "Bash"
 ],
 [
  "2026-09-14T15:58:48.550Z",
  "PostToolBatch",
  null
 ],
 [
  "2026-09-14T15:58:51.174Z",
  "MessageDisplay",
  null
 ],
...
dialog-probe.txt exists: True
```
Prompt-suggestion ghost text (`supp2-20260914T155625Z/A1-suggestion.txt` and `.ansi.cat-v.txt`):
```text
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ cat hello.txt
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
^[[39mM-bM-^]M-/M-BM- ^[[2mcat hello.txt^[[0m
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| typed text at a permission dialog | keystrokes | always | discarded; not echoed, no hook | |
| Enter at a permission dialog | keystroke | always | selects the highlighted option, which defaults to `1. Yes` | the tool ran and the file was created |
| ghost suggestion | pane text | sometimes (1–4 turns in) | `cat hello.txt`, `edit notes.txt` | in `-p` output indistinguishable from typed input; in `-e` output wrapped in SGR `2` (dim) … `0` |
| bare Enter on a ghost suggestion | keystroke | observed once | nothing submitted (no hook within 8 s), ghost stays (`A2-after-bare-enter.txt`, `A2-hooks-after-bare-enter.json` = `[]`) | |
| typed text over a ghost | keystrokes | observed once | replaces the ghost; submitted verbatim | `supp3-*/A3-hooks-after-enter.json` |

**Variants and edge cases:**
- Not verified: text beginning with a digit (`1`/`2`/`3`) at a permission dialog, which presumably selects an option directly; `Esc`; `Tab to amend`.
- A pane-scraper that reads the input box with plain `capture-pane -p` will mistake ghost text for a draft. It must use `-e` and check for SGR 2.

**Spec alignment:**
- Spec line 1168 says "`needs_you` | write immediately (it is *asking* you)". When `needs_you` comes from a permission prompt, a programmatic message plus Enter is **not delivered and approves the pending tool call**. A write in this state must be refused or routed as an explicit answer, never as text (`supp2-20260914T155625Z/B-hooks.json`, `B-file-created.txt`).

---

## Transcript entries written by TUI input: queue-operation, queued_command, compact_boundary

- **Produced by:** Claude Code 2.1.270, interactive (transcript `~/.claude/projects/<slug>/<session_id>.jsonl`)
- **Consumed by:** §9 mailbox (D12); §8 transcript tail classifier (D24); M2, M3
- **Probe:** `probe_tui.py` steps 5, 8, 9 (lines copied by grep into the evidence file). Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`)
```json
{"type":"queue-operation","operation":"enqueue","timestamp":"2026-09-14T15:51:41.227Z","sessionId":"71757dd1-5375-4801-b467-7898a0bc1194","content":"Reply with only the word SECOND"}
{"type":"queue-operation","operation":"remove","timestamp":"2026-09-14T15:51:50.854Z","sessionId":"71757dd1-5375-4801-b467-7898a0bc1194","content":"Reply with only the word SECOND","reason":"absorbed_mid_turn"}
{"parentUuid":"b159063b-eff0-4bd5-8610-742116ceb184","isSidechain":false,"attachment":{"type":"queued_command","prompt":"Reply with only the word SECOND","source_uuid":"2891166f-e7ff-439e-aced-2766a1597762","commandMode":"prompt","origin":{"kind":"human"},"timestamp":"2026-09-14T15:51:41.227Z"},"type":"attachment","uuid":"69b673dc-a637-4197-a121-7f23f81536da","timestamp":"2026-09-14T15:51:41.227Z","rendered":[{"content":"<system-reminder>\nThe user sent a new message while you were working:\nReply with only the wor...
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `type` | string | always | `queue-operation` | |
| `operation` | string | always | `enqueue`, `remove` | |
| `reason` | string | sometimes (remove only) | `absorbed_mid_turn` | |
| `content` | string | always | the queued text | |
| `timestamp`, `sessionId` | string | always | | |
| `attachment.type` | string | always | `queued_command` | on an `attachment` entry |
| `attachment.origin.kind` | string | always | `human` | tmux send-keys is recorded as a human |
| `attachment.commandMode` | string | always | `prompt` | |
| `rendered[].content` | string | always | `<system-reminder>\nThe user sent a new message while you were working:...` | what the model saw |

**Variants and edge cases:**
- `enqueue` at 15:51:41.227, `remove` at 15:51:50.854. The removal happened right after the running `sleep 12` tool result.

**Spec alignment:** the spec does not describe these entries. They are the transcript-side evidence that a write landed mid-turn. Not a mismatch; a gap.

---

## Session title: /rename and --name (custom-title, agent-name, session_title, pane_title)

- **Produced by:** Claude Code 2.1.270. `/rename <title>` typed into the TUI over tmux; `claude --name <title>` at spawn; headless `claude --resume <id> -p "/rename <title>"`
- **Consumed by:** §7.1 lines 700–736, D29 (line 134), `EngineCapabilities.can_set_title` (line 496), `EngineAdapter.set_title` (line 438), §18 line 2331; M3
- **Probe:** `probe_tui.py` step 8, `probe_tui_supp.py`, `probe_headless_parity.py` h4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/10-rename-transcript-new-lines.jsonl`)
```json
{"type":"custom-title","customTitle":"shp-probe-title-1","sessionId":"71757dd1-5375-4801-b467-7898a0bc1194"}
{"type":"agent-name","agentName":"shp-probe-title-1","sessionId":"71757dd1-5375-4801-b467-7898a0bc1194"}
{"parentUuid":"4c115cc5-2455-480a-9a0c-86a87cbc0ba7","isSidechain":false,"type":"system","subtype":"local_command","content":"<command-name>/rename</command-name>\n            <command-message>rename</command-message>\n            <command-args>shp-probe-title...
{"parentUuid":"9a05eea3-487d-4abe-a667-ffccc136d174","isSidechain":false,"promptId":"bc5cfd55-024b-4810-8d8d-a6588ce30be9","type":"user","message":{"role":"user","content":"<system-reminder>\nThe user named this session \"shp-probe-title-1\". This may indicate the session's focus or intent.\n</syste...
```
Visible to tmux and the sidecar (`10-rename-before-fmt.txt`, `10-rename-after-fmt.txt`, `10-rename-hooks.txt`, `10-sidecar-after-rename.json`):
```text
pane_title=✳ PONG response
pane_title=✳ shp-probe-title-1
hook events during /rename: []
...,"name":"shp-probe-title-1","nameSource":"user","nameSince":1789401166976,"s...
```
The same done headless (`headless-20260914T160308Z/h4-transcript-custom-title-lines.jsonl`):
```json
{"type":"custom-title","customTitle":"shp-headless-title","sessionId":"55b21a24-e35c-4121-b504-1c3d12a75d3e"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `custom-title.customTitle` | string | always on rename | `shp-probe-title-1` | written by Claude Code itself |
| `agent-name.agentName` | string | always on rename | same | |
| `system/local_command` | entry pair | always on rename | `<command-name>/rename</command-name>...`, `<local-command-stdout>Session renamed to: ...` | |
| `user` `isMeta:true` | entry | always on rename | `The user named this session "..."` | the model is told about the name |
| `ai-title.aiTitle` | string | sometimes | `PONG response` | engine title, written after the first turn |
| hook `session_title` | string | sometimes | on later `SessionStart` (compact, fork, `--name` startup) and `UserPromptSubmit` | **no hook fires at rename time** |
| `#{pane_title}` | string | always | `<redacted: host name>` (before TUI) → `✳ Claude Code` → `✳ PONG response` (engine title) → `✳ shp-probe-title-1` (user title) | readable with tmux alone |
| sidecar `name` / `nameSource` | string | always while alive | `shp-tui-a-4tvrx00n-00`/`derived` → `shp-probe-title-1`/`user` | `--name` at spawn gives `nameSource: user` |

**Variants and edge cases:**
- Once a user title exists, `pane_title` did not revert to the engine title (a second `ai-title` entry was appended later, and `pane_title` stayed `✳ shp-probe-title-1` in `13-list-sessions-after-exit.txt`).
- A fork inherits the user title: transcript `custom-title` and sidecar `nameSource: user`. Two sessions then share one title, and `/exit` suggests `claude --resume "shp-probe-title-1"`, which is ambiguous (`13-dead-pane.txt`).
- Headless `/rename` on a resumed session worked (`h4_rename.stdout.json` result `Session renamed to: shp-headless-title`). It emitted `SessionStart{resume}` and `SessionEnd{other}`. Not verified: doing this against a session that is live in another process (the attached case).

**Spec alignment:**
- Spec lines 724–731 give the candidate mechanism as "appending an `ai-title` entry to the session transcript", and `can_set_title` is `False` "until the probe in §18 says otherwise". In reality the engine itself writes `custom-title` (not `ai-title`) when `/rename` is typed over the pty, or when spawned with `--name`, so Shepherd never writes the file. For **owned** sessions `can_set_title` can be `True`. `title_synced_at` can be set from the `custom-title` entry, the sidecar `nameSource:"user"`, or `#{pane_title}` (`run-20260914T154946Z/10-*`, `supp-20260914T155346Z/02-sessionstart-and-sidecar.txt`).
- Spec line 713–715 (`engine` title from `ai-title`): aligned (`07-10-11-transcript-excerpt.jsonl`).
- Spec line 2331: answered as above.

---

## Session sidecar file ~/.claude/sessions/<pid>.json

- **Produced by:** Claude Code 2.1.270, interactive, one file per live process, removed at exit
- **Consumed by:** not in spec. Relevant to §8 `state` (lines 933–945), §9 LocalRunner `probe()`, §7.1 title; M1 (attached discovery), M3
- **Probe:** `probe_tui.py` (sidecar snapshots at each step). Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14 (throwaway sessions only; the user's own sidecars were not read)

**Real example** (full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/06-sidecar-permission.json`)
```json
{"pid":4041880,"sessionId":"71757dd1-5375-4801-b467-7898a0bc1194","cwd":"/tmp/shp-tui-A-4tvrx00n","startedAt":1789401012996,"procStart":"543824210","version":"2.1.270","peerProtocol":1,"peerFeatures":["notify_idle","reply_across_default_dirs","artifact_yield"],"kind":"interactive","entrypoint":"cli","pidDomain":"linux:<redacted: machine-id>:pid:[4026531836]","tmux":"probe_a:@0.%0","messagingSocketPath":"/tmp/cc-socks/4041880.sock","name":"shp-tui-a-4tvrx00n-00","nameSource":"derived","nameSince":1789401012996,"status":"waiting","updatedAt":1789401085541,"statusUpdatedAt":1789401085541,"waitingFor":"permission prompt"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `pid` | int | always | equals tmux `#{pane_pid}` | |
| `sessionId` | string | always | | |
| `cwd` | string | always | | |
| `startedAt`, `nameSince`, `updatedAt`, `statusUpdatedAt` | int (epoch ms) | always | | |
| `procStart` | string | always | | |
| `version` | string | always | `2.1.270` | |
| `peerProtocol` | int | always | `1` | |
| `peerFeatures` | array | always | `["notify_idle","reply_across_default_dirs","artifact_yield"]` | |
| `kind` | string | always | `interactive` | |
| `entrypoint` | string | always | `cli` | |
| `pidDomain` | string | always | `linux:<hex>:pid:[<ns>]` | the hex equals this host's `/etc/machine-id` (checked by the auditor); treat as a host identifier |
| `tmux` | string | always (in tmux) | `probe_a:@0.%0`, `probe_fork:@2.%2` | `session:@window.%pane` as the engine sees it |
| `messagingSocketPath` | string | always | `/tmp/cc-socks/<pid>.sock` | |
| `name` / `nameSource` | string | always | `derived`, `user` | |
| `status` | string | always | `idle`, `busy`, `waiting` | |
| `waitingFor` | string | sometimes | `permission prompt` | only with `waiting` |
| `bridgeSessionId` | string | never observed (in cited captures) | | the prober reports it appeared with Remote Control on in a discarded, uncited exploratory run; not verified by any capture here |

**Variants and edge cases:**
- Absent during the trust dialog (`01-trust-dialog-sidecar.json`). Removed after `/exit` (`13-fork-sidecar-after-exit.json`) and after `kill-session` (`15-pid-after-kill.txt`).
- `busy` during a running tool (`07-sidecar-running.json`). `idle` again after `Stop` (`03-sidecar-after-stop.json`).
- `status` stayed `idle` across the 60 s `idle_prompt` notification (`04-sidecar-idle.json`).

**Spec alignment:** a gap. The spec does not know this file. It is an engine-owned, non-hook source of `idle/busy/waiting` and the title, which could back `Runner.probe()` and attached-session discovery. Reading it does not conflict with principle 4 (read-only).

---

## tmux list-sessions -F pane state (remain-on-exit on)

- **Produced by:** tmux 3.4 (`tmux -L shepherd-probe list-sessions -F ...`) with `set-option -w remain-on-exit on`
- **Consumed by:** §9 LocalRunner (D14) `probe()`, `exit_code` (§7 line 693), `crashed` rule line 964; M3
- **Probe:** `probe_tui.py` steps 1b, 11–13. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/14-list-sessions-after-sigterm.txt`)
```text
# format: #{session_name}|#{pane_pid}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}|#{alternate_on}|#{pane_width}x#{pane_height}|#{pane_title}
# rc=0 stderr=
probe_a|4041880|0|||1|160x45|✳ shp-probe-title-1
probe_b|4041912|1|1||0|160x45|
probe_fork|4042432|1|0||0|160x45|
probe_sig|4042531|1|143||0|160x45|
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `#{session_name}` | string | always | `probe_a`, `probe_b`, `probe_fork`, `probe_sig` | |
| `#{pane_pid}` | int | always | the claude pid (tmux runs the command via exec) | equals the sidecar `pid` and the hook `_claude_pid` |
| `#{pane_dead}` | 0/1 | always | `0` alive, `1` exited | |
| `#{pane_dead_status}` | int | sometimes (dead only) | `0` (/exit), `1` (trust refused), `143` (SIGTERM) | empty while alive |
| `#{pane_dead_signal}` | int | never observed | empty even after SIGTERM | claude handled the signal and exited 143 |
| `#{alternate_on}` | 0/1 | always | `1` live TUI; `0` trust dialog or dead pane | |
| `#{pane_width}x#{pane_height}` | string | always | `160x45` | |
| `#{pane_title}` | string | always | `✳ shp-probe-title-1`, empty on a dead pane | |

**Variants and edge cases:**
- `kill-session` removes the row entirely (`15-list-sessions-after-kill.txt`), so no exit status survives. Record the kill before issuing it.
- On a dead pane, `capture-pane` shows tmux's own line `Pane is dead (status 0, Mon Sep 14 15:53:21 2026)` (`13-dead-pane.txt`).
- The `=<name>:` target form worked for every pane command. Names without `:` were accepted unchanged.
- The socket directory on this host holds sockets named `default`, `shepherd`, `shepherd-probe`, `shepherd-spike`, `shp-schemas-fork`, `shp-schemas-tx`, `shp-spike-9bc1f3` (`run-20260914T154946Z/tmux-socket-names.txt`).

**Spec alignment:**
- Spec line 1135 puts owned sessions on `tmux -L shepherd`. A socket named `shepherd` already exists on this host (`run-20260914T154946Z/tmux-socket-names.txt`, names only). The capture does not show what runs on it. At audit time a read-only `ps` showed a live `tmux -L shepherd new-session -d -s main ...` server owned by the user, not by any probe. So Shepherd's socket name collides with an existing server and should be configuration.
- Spec line 964: `crashed` = "process exit ≠ 0 with no preceding `Stop`/`StopFailure`". The SIGTERM'd session was never prompted, emitted no `Stop`, and exited 143, so it matches `crashed` unless `killed` (line 965, action log) is checked first. A refused trust dialog exits 1 with no hook at all and also matches `crashed`, although nothing crashed: the session was blocked on a dialog (`14-list-sessions-after-sigterm.txt`, `01b-list-sessions-after-refuse.txt`, `hooks-a.jsonl` lines 35–36).

---

## tmux capture-pane output (-p, -e, -S -2000) for the Claude Code TUI

- **Produced by:** tmux 3.4 `capture-pane` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 Terminal fidelity (lines 1140, 1147–1160), `Runner.snapshot()` (line 426), D14; M3
- **Probe:** `probe_tui.py`, `probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/04-scrollback-stats.txt` and `04-capture-S2000.txt`)
```text
format '#{alternate_on} #{history_size} #{history_limit} #{pane_height}' -> 1 0 2000 30
capture -S -2000 lines=30 visible lines=30
'1' present in -S -2000 capture: False; '80' present: True
ESC count in -e capture: 12
```
First lines of `capture-pane -p -S -2000` after an 80-line answer in a 30-row pane (`supp-20260914T155346Z/04-capture-S2000.txt`):
```text
  58
  59
  60
...
```
`-e` output keeps SGR colours and OSC 8 hyperlinks (`run-20260914T154946Z/01-trust-dialog.ansi.cat-v.txt` line 12):
```text
 ^[[38;5;246m^[]8;id=zaxmda;https://code.claude.com/docs/en/security^[\Security guide^[[39m^[]8;;^[\
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| visible screen | text | always | exactly `pane_height` lines | |
| scrollback (`-S -2000`) on the alternate screen | text | never observed | `history_size` 0; the capture = the 30 visible lines | earlier output is gone from tmux |
| SGR sequences | bytes | always with `-e` | `38;5;N`, `48;5;N`, `1`, `2`, `0`, `39`, `49` | |
| OSC 8 hyperlink | bytes | sometimes | `ESC]8;id=...;https://code.claude.com/docs/en/security ESC\` | |
| input-box line | text | always | `❯` + NBSP + text, between two `────` rules | the NBSP (`M-BM- `) follows `❯` |
| border title | text | sometimes | `──── shp-probe-title-1 ─` on the upper rule after rename | `10-rename-after.txt` |

**Variants and edge cases:**
- Claude Code prints `tmux detected · scroll with PgUp/PgDn · or add 'set -g mouse on' to ~/.tmux.conf for wheel scroll`. That line appears in `run-20260914T154946Z/03-after-stop.txt` line 41 and `12-fork-started.txt` line 41. The TUI keeps its own scroll, which tmux cannot see.
- The TUI redraws the conversation on the alternate screen, so late attach shows the recent part of the conversation, not the start.

**Spec alignment:**
- Spec line 1140 says `capture-pane -e -p -S -2000` "returns the current screen **with ANSI intact** plus scrollback". The ANSI part is aligned. There is **no scrollback** while the TUI is on the alternate screen (`history_size` 0), so a late-attaching client gets only the visible rows. Earlier output must come from the transcript or from a server-side log of `pipe-pane` (`supp-20260914T155346Z/04-scrollback-stats.txt`).
- Spec line 1142 (alternate screen): aligned (`alternate_on=1`, `run-20260914T154946Z/02-after-trust-fmt.txt`).

---

## tmux pipe-pane live byte stream

- **Produced by:** tmux 3.4 `pipe-pane -o "cat >> file"` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 Terminal fidelity "live byte stream" (line 1152), `Runner.attach()` (line 425); M3
- **Probe:** `probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/03-pipe-pane.raw`, rendered through `cat -v` in `03-pipe-pane-head.cat-v.txt`)
```text
^[[?25l^[[H^M^[[2C^[[27BPrint^[[9Gthe^[[13Gintegers^[[22Gfrom^[[27G1^[[29Gto^[[32G80,^[[36Gone^[[40Gper^[[44Gline,^[[50Gnothing^[[58Gelse.^M^[[18C^[[2B^[[K^[[30;1H^[[28;63H^[[?25h^[[?25l^[[H^M^[[8B^[[48;5;237m^[[38;5;239mM-bM-^]M-/ ^[[38;5;231mPrint the integers from 1 to 80, one per line, nothing else.^[[39m                                                          ^M^[[16B^[[49m^[[38;5;174mM-bM-^\M-;^[[3GLo^[[38;5;2...
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| cursor hide/show | CSI | always | `ESC[?25l` … `ESC[?25h` around every frame | |
| absolute/relative moves | CSI | always | `ESC[H`, `ESC[nB`, `ESC[nC`, `ESC[nG`, `ESC[r;cH` | a diff-render, not a line stream |
| colours | SGR | always | `38;5;N`, `48;5;N` | |
| size | bytes | always | 4839 bytes for one short turn | `04-scrollback-stats.txt` |

**Variants and edge cases:** the stream is only meaningful to a terminal emulator (xterm.js). Text cannot be grepped out of it, because words are placed by cursor moves (`Print^[[9Gthe^[[13Gintegers`).

**Spec alignment:** aligned with lines 1149–1152 (snapshot, then live bytes, then xterm.js).

---

## tmux resize-window reflow

- **Produced by:** tmux 3.4 `resize-window -t =probe_a: -x 70 -y 30` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 line 1142, `Runner.resize()` (line 428), D14; M3
- **Probe:** `probe_tui.py` step 7. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/09-resize-after-70x30.txt`, stats `09-resize-fmt.txt`)
```text
pane=70x30 window=70x30
max captured line length=70 lines=30
❯ Use the Bash tool to run exactly: sleep 12 ; then reply with only
  DONE-ONE

  Ran 1 shell command

❯ Reply with only the word SECOND

● SECOND

✻ Brewed for 19s · done 3:51 PM

──────────────────────────────────────────────────────────────────────
❯ 
──────────────────────────────────────────────────────────────────────
  ⏸ manual mode on · ? for shortcuts · ← for agents
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| pane/window size | `WxH` | always | `70x30` after resize | |
| max captured line length | int | always | `70` | no line exceeds the width |
| wrapped prompt | text | sometimes | `...reply with only` / `  DONE-ONE` | the TUI re-wraps with a 2-space indent |
| rules | text | always | `────` redrawn at 70 columns | |

**Variants and edge cases:** resizing back to 160x45 restored the layout (the following steps captured normally).

**Spec alignment:** aligned with line 1142 and D14.

---

## ask() via fork: claude --resume <id> --fork-session in a second tmux session

- **Produced by:** Claude Code 2.1.270, interactive, `claude --resume <id> --fork-session` in pane `probe_fork` while the original ran idle in `probe_a`
- **Consumed by:** §9 `ask()` lines 1197–1216, D13 (line 116), `can_fork` (line 495), §7 `origin=ask_fork` / `ephemeral` (lines 657–659), §18 line 2326; M3
- **Probe:** `probe_tui.py` step 10 + `analyze_fork.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/12-fork-summary.json`)
```json
{
 "original_session_id": "71757dd1-5375-4801-b467-7898a0bc1194",
 "fork_session_id": "c3f63742-5ff5-44ea-8f6e-a26d027b51d0",
 "original_transcript": "/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl",
 "fork_transcript": "/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/c3f63742-5ff5-44ea-8f6e-a26d027b51d0.jsonl",
 "before": {
  "sha": "481298ac7988e6a063d6c5b22b2ac2f6452286a0e94dcfe9c9c5ec7c46650872",
  "lines": 85,
  "files": [
   "71757dd1-5375-4801-b467-7898a0bc1194",
   "71757dd1-5375-4801-b467-7898a0bc1194.jsonl",
   "memory"
  ]
 },
 "fork_started_no_prompt": {
  "fork_transcript_exists_before_prompt": false,
  "files": [
   "71757dd1-5375-4801-b467-7898a0bc1194",
   "71757dd1-5375-4801-b467-7898a0bc1194.jsonl",
   "memory"
  ]
 },
 "after_fork_turn": {
  "sha": "481298ac7988e6a063d6c5b22b2ac2f6452286a0e94dcfe9c9c5ec7c46650872",
  "lines": 85,
  "files": [
   "71757dd1-5375-4801-b467-7898a0bc1194",
   "71757dd1-5375-4801-b467-7898a0bc1194.jsonl",
   "c3f63742-5ff5-44ea-8f6e-a26d027b51d0.jsonl",
   "memory"
  ]
 },
 "original_unchanged": true,
 ...
 "hook_events_for_original_session_during_fork": []
}
```
Fork transcript structure (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/12-fork-structure.txt`) and the fork's first lines (`12-fork-transcript-head3.jsonl`):
```text
...
fork entries whose uuid also exists in original: 16 of 29
...
original compact_boundary line indexes: [76]
fork compact_boundary line indexes: [7]
...
fork entries carrying both keys -> (type, subtype, session_id is original?, sessionId is fork?): {('user', None, True, True): 4, ('assistant', None, True, True): 2, ('system', 'stop_hook_summary', True, True): 1, ('attachment', None, True, True): 4, ('attachment', None, False, True): 5, ('assistant', None, False, True): 2, ('system', 'stop_hook_summary', False, True): 1}
original entries with session_id key: 34 all equal to original id: True
```
```json
{"type":"custom-title","customTitle":"shp-probe-title-1","sessionId":"c3f63742-5ff5-44ea-8f6e-a26d027b51d0"}
{"type":"ai-title","aiTitle":"PONG response","sessionId":"c3f63742-5ff5-44ea-8f6e-a26d027b51d0"}
{"type":"agent-name","agentName":"shp-probe-title-1","sessionId":"c3f63742-5ff5-44ea-8f6e-a26d027b51d0"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| fork `session_id` | uuid | always | new (`c3f63742-...`) | in `SessionStart{source:fork}` at launch |
| fork transcript file | path | sometimes | **absent until the first prompt**, then `<projdir>/<fork id>.jsonl` | |
| original transcript | file | always | sha256 unchanged, 85 lines before and after the fork turn | `original_unchanged: true` |
| hooks for the original during the fork | list | never observed | `[]` | the target was not touched |
| copied entries `sessionId` | string | always | rewritten to the fork id | |
| copied entries `session_id` | string | sometimes | still the **original** id on copied entries (11 lines) | the only parent link found; no `forkedFrom` key |
| copied range | entries | always | from the original's last `compact_boundary` onward | pre-compact history is not carried |
| title | string | sometimes | inherits the user title (`custom-title`, sidecar `nameSource:user`) | |

**Variants and edge cases:**
- The fork answered from post-compact context only (`12-fork-answer.txt`).
- `/exit` in the fork left its transcript on disk. `--no-session-persistence` "only works with --print" per `claude --help` (`run-20260914T154946Z/claude-help-excerpt.txt`), so discarding the fork means deleting the file or using `-p`.
- The original's transcript was 85 lines both before and after the fork turn. It was 87 lines when `analyze_fork.py` ran after teardown; those 2 lines were appended after the fork measurement, and which step appended them was not isolated.
- Headless `--resume <id> --fork-session -p` produced the same `SessionStart{fork}` shape (`headless-20260914T160308Z/event-sequence.txt`).

**Spec alignment:**
- Spec line 1204–1205 (`start_reason` includes `fork`): the field is `source` (`run-20260914T154946Z/hooks-a.jsonl` line 30).
- Spec line 1203 says "discard the fork". A TUI fork persists a transcript (and inherits the user title, so it shows up in `/resume` under the same name). Discarding it is an explicit cleanup step (`run-20260914T154946Z/12-fork-summary.json` `after_fork_turn.files`; the fork transcript was still present, 53 lines, when `12-fork-structure.txt` was computed after teardown). The spec does not say how "discard" is done, so this is a gap, not a contradiction. The fork carries only the post-compact history, but that is also all the target's own live context holds.
- Spec line 1207 says "the target is never interrupted, its context is never polluted": aligned. The original sha256 was unchanged and no hooks fired for it.
- Spec line 2326 (verify fork path in M3): answered. `can_fork = True` for Claude Code.
