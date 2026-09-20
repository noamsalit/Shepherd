# Spec lines that still assert what the plan's "Ground Truth That Overrides the Spec" (plan L81-112) says is false
Readings taken 2026-09-14: spec at working tree (uncommitted edits included); probe data re-parsed
(probe-event-keys-2026-09-14.txt); claude 2.1.270 bundle schemas (bundle-*.txt).

| # | Spec line | Spec asserts | Contradicted by |
|---|---|---|---|
| 1 | §7 L529 | repos_touched "accumulated from FileChanged" | plan GT2 / DV-06; probe: FileChanged never fired |
| 2 | §7 L530 | pr_url "free - the transcript emits pr-link entries" | plan GT6 / DV-08 |
| 3 | §8 L732 | Notification / PermissionRequest -> needs_you | plan GT2 / DV-07 |
| 4 | §8 L735 | FileChanged appends to repos_touched | plan GT2 / DV-06 |
| 5 | §8 L736 | Stop / StopFailure / SessionEnd triggers classification | StopFailure never fired (GT2) |
| 6 | §8 L761-772 | 24 events subscribed, incl. 12 never fired | plan DV-04 registers 14 |
| 7 | §8 L778-780 | common fields on EVERY event incl. prompt_id, permission_mode, effort.level | probe: SessionStart carries only cwd, hook_event_name, session_id, source, transcript_path |
| 8 | §8 L786, L794 | needs_you from Notification.notification_type in a 5-value enum | bundle: notification_type:o() (free string); never fired |
| 9 | §8 L788 | running = signal within LIVENESS_WINDOW_S (90) | plan DV-09 (attached) |
| 10 | §8 L800, L805, L820, §18 L2168 | StopFailure.error_type | bundle: StopFailure{error, error_details, last_assistant_message} - field is `error` |
| 11 | §8 L811-812, L825, L874 | Stop.stop_reason (max_tokens / tool_use / end_turn) | plan GT1; bundle Stop{stop_hook_active,last_assistant_message,background_tasks,...} no stop_reason |
| 12 | §8 L816-819 | SessionEnd.end_reason | plan GT1 / DV-05; bundle: reason in [clear,resume,logout,prompt_input_exit,other]; `other` unmapped by §8 |
| 13 | §9 L1051 | "SessionStart hook's start_reason enum includes fork" | bundle: field is `source`, enum [startup,resume,clear,compact,fork] |
| 14 | §7 L540 | decided_by enum mechanical/model/declared/manual | D34 L138 and §8 L863 say decided_by='heuristic' (plan DV-10 notes conflict) |
| 15 | §7.1 L573-580, §18 L2169 | title write-back candidate = append ai-title; probe pending in M3; can_set_title False for every engine | docs/probes/2026-09-13-tmux-tui-spike.md: /rename over pty PASS, engine writes custom-title |
| 16 | §18 L2168 | hook payload fields "documented, not observed"; "M1, first task" | probe already run (77 events); spec row not updated |
| 17 | §0 L27-30, §18 L2163 | tmux spike still to run before M3 | spike PASS 2026-09-13 |
| 18 | §7 L673-674, §18 L2170 | FULL OUTER JOIN "Verify in M1" | plan DV-27 answered; re-checked 3.45.1 today |
| 19 | App. A L2294 | attached session needs_you_reason "idle - waiting for your next instruction" | plan DV-07 (cannot be produced) |
| 20 | App. A L2365 | stop_event {hook: Stop, stop_reason: end_turn} | plan GT1 |
| 21 | §7 L513 | attached brief = transcript lastPrompt | reading: lastPrompt truncated to 200 chars + "…" (lastprompt-vs-user-prompt.txt); plan PD-10 uses UserPromptSubmit.prompt yet claims equality |
