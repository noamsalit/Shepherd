#!/usr/bin/env python3
# Writes a throwaway project settings.json with capture hooks on every event of interest and cc10x disabled.
import json, sys
hook_py, out_jsonl, dest = sys.argv[1], sys.argv[2], sys.argv[3]
events = ["SessionStart","UserPromptSubmit","PreToolUse","PostToolUse","SubagentStart","SubagentStop",
          "Stop","StopFailure","SessionEnd","PreCompact","PostCompact","Notification","TaskCreated","TaskCompleted"]
hooks = {e: [{"matcher": "*", "hooks": [{"type": "command", "command": f"python3 {hook_py} {e} {out_jsonl}"}]}] for e in events}
json.dump({"hooks": hooks, "enabledPlugins": {"cc10x@cc10x": False}}, open(dest, "w"), indent=1)
