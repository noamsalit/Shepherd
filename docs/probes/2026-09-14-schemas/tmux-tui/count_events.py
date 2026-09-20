#!/usr/bin/env python3
"""Count needs-you / subagent hook events per capture file. Usage: count_events.py <hooks.jsonl>..."""
import json, sys
for fn in sys.argv[1:]:
    hs = [json.loads(l) for l in open(fn)]
    c = lambda p: sum(1 for h in hs if p(h))
    print(fn, "PermissionRequest:", c(lambda h: h["_event"] == "PermissionRequest"),
          "Notification(permission_prompt):", c(lambda h: h["payload"].get("notification_type") == "permission_prompt"),
          "Notification(idle_prompt):", c(lambda h: h["payload"].get("notification_type") == "idle_prompt"),
          "SubagentStart:", c(lambda h: h["_event"] == "SubagentStart"),
          "SubagentStop:", c(lambda h: h["_event"] == "SubagentStop"),
          "payloads with an 'effort' key:", c(lambda h: "effort" in h["payload"]))
    for h in hs:
        if h["_event"] in ("PermissionRequest", "PostToolUse") or h["payload"].get("notification_type") == "permission_prompt":
            print("  ", h["_captured_at"], h["_event"], h["payload"].get("notification_type") or "")
