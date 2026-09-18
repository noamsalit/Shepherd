#!/usr/bin/env python3
"""Write a throwaway settings.json that registers capture_hook.sh for every hook event
Claude Code 2.1.270 knows (list extracted from the binary), and disables the cc10x plugin.
Usage: make_settings.py <out settings.json> <hook log.jsonl> <claude version>"""
import json, os, sys
EVENTS = ["PreToolUse","PostToolUse","PostToolUseFailure","PostToolBatch","Notification",
 "UserPromptSubmit","UserPromptExpansion","SessionStart","SessionEnd","Stop","StopFailure",
 "SubagentStart","SubagentStop","PreCompact","PostCompact","PreModelSwitch","PostModelSwitch",
 "PermissionRequest","PermissionDenied","Setup","TeammateIdle","TaskCreated","TaskCompleted",
 "Elicitation","ElicitationResult","ConfigChange","WorktreeCreate","WorktreeRemove",
 "InstructionsLoaded","CwdChanged","FileChanged","DirectoryAdded","MessageDisplay"]
out, log, ver = sys.argv[1], sys.argv[2], sys.argv[3]
cap = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_hook.sh")
hooks = {ev: [{"hooks": [{"type": "command",
          "command": f"SHP_CLAUDE_VERSION='{ver}' {cap} {ev} {log}", "timeout": 10}]}]
         for ev in EVENTS}
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump({"enabledPlugins": {"cc10x@cc10x": False}, "hooks": hooks}, open(out, "w"), indent=1)
print(out)
