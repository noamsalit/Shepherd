# Transcript / filesystem claims under test (extracted 2026-09-14)

Plan = docs/plans/2026-09-13-m1-foundation-visibility-plan.md ; Spec = docs/specs/orchestrator-platform.md

C01 plan:94  transcript path ~/.claude/projects/<slug>/<engine_session_id>.jsonl
C02 plan:94,1602,1611  slug = cwd with every non-alphanumeric char -> '-' ; /tmp/claude-0/-root-Shepherd/x -> -tmp-claude-0--root-Shepherd-x
C03 plan:95  subagent transcripts at <slug>/<sid>/subagents/agent-<agent_id>.jsonl
C04 plan:96  .meta.json next to it: {agentType, description, toolUseId, spawnDepth, requestShape}
C05 plan:98  ai-title{aiTitle}, custom-title{customTitle}, last-prompt{lastPrompt}, agent-name
C06 plan:99  assistant carries message.model and top-level effort (string); user, attachment, system, file-history-snapshot
C07 plan:92  effort in transcript is top-level string "high"
C08 plan:100 / DV-08 plan:127  no pr-link entry anywhere  (spec:530 says transcript emits pr-link)
C09 plan:101 / A4 plan:177  --resume keeps session_id and transcript file
C10 plan:1603  locate_transcript_in globs projects_dir/*/<id>.jsonl, id must match UUID regex
C11 plan:1604  path allowed only under realpath(projects_dir) and .jsonl
C12 plan:1605  parse_signals: ignores isSidechain:true entries
C13 plan:1606 / PD-09 plan:164  subagent finished iff parent transcript user entry message.content[*].type=="tool_result" with tool_use_id == meta.toolUseId and requestShape != "background"
C14 plan:1606  started_at/last_activity_at from first/last `timestamp` in agent jsonl
C15 plan:165 PD-10  brief = latest UserPromptSubmit.prompt == transcript lastPrompt
C16 plan:166 PD-11  transcript reads on SessionStart/Stop/SessionEnd get title, model, effort
C17 plan:1553/DV-25  newest custom-title beats newest ai-title
C18 plan:1591  fixture includes one background agent (requestShape=background)
C19 hook payloads carry transcript_path (plan:93) and SubagentStop.agent_transcript_path (plan:90) consistent with C01/C03
C20 spec:513  brief for attached = transcript's lastPrompt
C21 spec:515  effort top-level transcript field; model at message.model
C22 spec:530  pr_url free: transcript emits pr-link entries
C23 spec:562  Claude Code writes ai-title entries -> engine title, including attached
C24 spec:458,739  subagent list read from transcript on demand
C25 spec:398  transcript JSONL at ~/.claude/projects/
C26 spec:779 hook common fields include effort.level (object)
C27 DDL session columns fed by transcripts: title, title_source, brief, model, effort, pr_url (plan:623-644)
C28 SUBAGENT_VIEW_FIELDS agent_id, agent_type, description, state, started_at, last_activity_at (plan:778)
C29 compaction: DV-30 SessionStart.source=="compact" (plan:148); no transcript compaction handling stated
