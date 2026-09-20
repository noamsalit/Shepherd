# Claim-by-claim comparison (probe-transcripts, 2026-09-14, claude 2.1.270)

Readings: existing-transcripts-analysis.json (30 jsonl under ~/.claude/projects, read-only), existing-meta-json.txt,
subagent-state-scan.txt, lastprompt-truncation.txt, compaction-entries.txt, fresh runs run1-4 (*-stdout.json),
hook-captures.jsonl (raw hook stdin + ancestry), fresh-probe-copies/ (copies of the fresh transcripts), slug-check.txt,
slug-long-unicode-check.txt. cc10x disabled via throwaway project settings: stop_hook_summary.hookInfos in the fresh
transcripts lists only the probe hook; no hook_success/hook_additional_context attachments appeared.

C01 path <slug>/<sid>.jsonl ............ ALIGNED (run1 hook transcript_path == file on disk)
C02 slug rule .......................... ALIGNED for "/tmp/shp-transcript-probe.7nMlKJ/my.proj_dir v1.2 test" and for non-ASCII (é,ü -> '-');
                                         MISALIGNED for cwd > 200 chars: real dir is 200-char prefix + "-5wwnj1" (len 207); rule gives len 255
C03 subagents/agent-<id>.jsonl ......... ALIGNED for Agent-tool subagents (incl. spawnDepth 2, stored flat); MISALIGNED for workflow subagents:
                                         <sid>/subagents/workflows/wf_<id>/agent-<id>.{jsonl,meta.json} + journal.jsonl
C04 meta fields ........................ PARTIAL: also parentAgentId, requestNonInteractive, model, workflowPhase; toolUseId ABSENT on workflow agents
C05 title/prompt/name types ............ ALIGNED (agent-name field is agentName); last-prompt without lastPrompt field seen 3x
C06 assistant message.model + effort ... ALIGNED for opus/sonnet; message.model == "<synthetic>" on 5 error entries; effort key absent on haiku (10/10)
C07 effort string ...................... ALIGNED ("high" 3458, "medium" 33)
C08 no pr-link ......................... ALIGNED (0 of 22 types) but UNVERIFIABLE as a general claim: no sampled session created a PR; `claude --help` has --from-pr
C09 resume keeps id + file ............. ALIGNED (run2: same session_id, same file 33 -> 42 lines, SessionStart.source=resume). --fork-session exists (help)
C10/C11 locate/glob/allowed ............ ALIGNED (glob */<uuid>.jsonl finds files; note other reviewers' probes also create dirs)
C12 isSidechain ........................ ALIGNED (main files all false; all subagent entries true; title/prompt entries carry no isSidechain)
C13 PD-09 finished rule ................ ALIGNED for foreground depth-1 (run1 tool_result id == meta.toolUseId). MISALIGNED for nested (tool_result only in
                                         parent AGENT transcript), workflow (no toolUseId), background (completion arrives as <task-notification> queue-operation/user string)
C14 timestamps in agent jsonl .......... ALIGNED (first line of all 16 agent files is user with timestamp)
C15/C20 brief == lastPrompt ............ MISALIGNED: lastPrompt <= 201 chars, ends with U+2026 when truncated (182x), never contains newlines
C16 reads on Start/Stop/End get title .. ALIGNED (run3 ai-title written at line 16 and 21, before stop_hook_summary line 23)
C17 custom beats ai .................... behaviour fine; rationale "user's rename inside Claude Code" MISALIGNED: --name writes custom-title at line 0 (run1),
                                         remote-control session name "remote" re-emitted 263x; no ai-title generated in named run1
C19 hook paths ......................... ALIGNED (transcript_path, agent_transcript_path match files)
C22 spec pr-link free .................. UNVERIFIED (see C08); spec text unchanged
C23 spec ai-title for attached ......... ALIGNED except named sessions (run1 produced none)
C29 compaction ......................... compact_boundary + isCompactSummary exist in-file, same sessionId (3 occurrences); triggers: manual 2, auto 1
EXTRA hook SessionStart/UserPromptSubmit carry `session_title` when the session is named (run1/run2), absent otherwise (run3)
EXTRA hook ancestry python3 -> sh -> claude (plan ground truth 8 left this unverified)
EXTRA 22 transcript entry types exist (plan lists 9): queue-operation, mode, permission-mode, bridge-session, atis-latch, file-history-delta, frame-link, cost-state, ...
EXTRA sidecar <sid>/custom-title.json {"customTitle": ...} exists next to a renamed session (tmux spike)
