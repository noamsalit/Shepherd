#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): MCP elicitation in the interactive TUI (spec 937 needs_you rule).
Does Notification.notification_type = elicitation_dialog / elicitation_url_dialog fire, together with the
Elicitation / ElicitationResult hooks? What does the dialog look like, and what reaches the MCP server?
Setup: stdio MCP stub (mcp_stub.py: ask_form = form-mode elicitation/create, ask_url = url-mode) added with
`claude mcp add -s user` into an isolated CLAUDE_CONFIG_DIR; local mock model that calls the tool; all hooks captured.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_elicitation_tui.py
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("elicitation-tui")
SOCK = "shp-gap-elicit"
assert tm(SOCK, "ls").returncode != 0
MLOG = R.path("mcp-stub-messages.jsonl"); HL = R.path("hooks.jsonl")
rules = {"rules": [
    {"match": "ELICIT-FORM", "require_tools": True, "not_tool_result": True, "tool_use": {"name": "mcp__shepherd__ask_form", "input": {}}},
    {"match": "ELICIT-URL", "require_tools": True, "not_tool_result": True, "tool_use": {"name": "mcp__shepherd__ask_url", "input": {}}},
], "default_text": "OK-MOCK", "default_after_tool": "OK-AFTER-TOOL"}
mock = MockEnv(R, "elicit", rules)
add = subprocess.run(["claude", "mcp", "add", "-s", "user", "shepherd", "--", sys.executable, os.path.join(HERE, "mcp_stub.py"), MLOG],
                     cwd=mock.work, env=mock.env_dict(), capture_output=True, text=True, timeout=60)
R.save("mcp-add.txt", f"rc={add.returncode}\n{add.stdout}{add.stderr}")
write_json(os.path.join(mock.work, ".claude", "settings.json"),
           settings_obj(HL, R.ver, extra={"permissions": {"allow": ["mcp__shepherd__*"]}}))
res = {}


def summary(n):
    out = []
    for h in hooks(HL)[n:]:
        p = h["payload"]; s = h["_event"]
        for k in ("notification_type", "tool_name", "mcp_server_name", "action", "mode"):
            if p.get(k):
                s += f"[{k}={p[k]}]"
        out.append(s)
    return out


t = Tui(R, SOCK, "shepherd_elicit", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
try:
    t.trust(); wait_event(HL, ev("SessionStart"), 30); time.sleep(3)
    for label, prompt, answer in (("form", "ELICIT-FORM ask me", "answer"), ("url", "ELICIT-URL ask me", "escape")):
        n = len(hooks(HL))
        t.submit(prompt)
        _, e = wait_event(HL, ev("Elicitation"), 30, after=n)
        time.sleep(3)
        R.save(f"{label}-dialog-screen.txt", t.screen())
        _, nt = wait_event(HL, lambda h: h["_event"] == "Notification" and "elicit" in (h["payload"].get("notification_type") or ""), 20, after=n)
        before_answer = summary(n)
        if answer == "answer":
            t.text("alpha"); time.sleep(0.8); R.save(f"{label}-dialog-typed-screen.txt", t.screen()); t.keys("Enter"); time.sleep(1.5)
            R.save(f"{label}-after-enter-screen.txt", t.screen())
            t.keys("Enter")  # submit button, if the form needs a second Enter
        else:
            t.keys("Escape")
        wait_event(HL, ev("Stop"), 30, after=n)
        time.sleep(2)
        R.save(f"{label}-after-screen.txt", t.screen())
        res[label] = {"events_before_answer": before_answer, "events_all": summary(n)}
        R.log(f"{label}: {json.dumps(res[label])}")
    R.save("results.json", json.dumps(res, indent=1))
finally:
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(res, indent=1))
