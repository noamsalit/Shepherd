#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): which permission-rule spellings allow an MCP tool in headless -p, and from
which source (project .claude/settings.json, --settings file, --allowedTools flag)? Companion to probe_config_scopes.py
(where project-settings rules in -p denied every spelling). The server is added with `claude mcp add -s user` into an
isolated CLAUDE_CONFIG_DIR; the model is a local mock that always calls mcp__shepherd__ping once.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_mcp_perm_p.py
"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("mcp-perm-p")
MLOG = R.path("mcp-stub-messages.jsonl")
rules = {"rules": [{"match": "MCP-PING", "match_body": "mcp__shepherd__ping", "require_tools": True, "not_tool_result": True,
                    "tool_use": {"name": "mcp__shepherd__ping", "input": {}}}], "default_text": "OK-MOCK", "default_after_tool": "OK-AFTER-TOOL"}
mock = MockEnv(R, "perm", rules)
BASE = {"enabledPlugins": {"cc10x@cc10x": False}, "remoteControlAtStartup": False}
env = mock.env_dict()
add = subprocess.run(["claude", "mcp", "add", "-s", "user", "shepherd", "--", sys.executable, os.path.join(HERE, "mcp_stub.py"), MLOG],
                     cwd=mock.work, env=env, capture_output=True, text=True, timeout=60)
R.save("mcp-add.txt", f"rc={add.returncode}\n{add.stdout}{add.stderr}")
res = {}


def run(label, cwd, args, project_settings=None, sep=True):
    os.makedirs(os.path.join(cwd, ".claude"), exist_ok=True)
    write_json(os.path.join(cwd, ".claude", "settings.json"), project_settings or BASE)
    nm = len(hooks(MLOG))
    cmd = ["claude", "-p", "--model", HAIKU, "--output-format", "json"] + args + (["--"] if sep else []) + ["MCP-PING call the tool"]
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    j = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
    calls = [m for m in hooks(MLOG)[nm:] if (m.get("msg") or {}).get("method") == "tools/call"]
    res[label] = {"argv_tail": args + (["--"] if sep else []), "project_settings_permissions": (project_settings or {}).get("permissions"),
                  "rc": p.returncode, "result": j.get("result"), "permission_denials": [d["tool_name"] for d in j.get("permission_denials", [])],
                  "stub_tools_call_count": len(calls), "stderr": p.stderr.strip()[:300]}
    R.log(f"{label}: {json.dumps(res[label])}")


def fresh(label):
    return mktmp(f"perm-{label}")


run("flag_allowedTools_without_separator_swallows_prompt", fresh("swallow"), ["--allowedTools", "mcp__shepherd__ping"], sep=False)
for spelling in ("mcp__shepherd", "mcp__shepherd__*", "mcp__shepherd__ping"):
    tag = spelling.replace("*", "STAR")
    run(f"flag_allowedTools[{spelling}]", fresh("flag"), ["--allowedTools", spelling])
    sp = write_json(os.path.join(mock.root, f"settings-{tag}.json"), dict(BASE, permissions={"allow": [spelling]}))
    run(f"settings_file[{spelling}]", fresh("sfile"), ["--settings", sp])
    run(f"project_settings_untrusted_dir[{spelling}]", fresh("proj"), [], project_settings=dict(BASE, permissions={"allow": [spelling]}))
# the same project-settings rule, in the dir the TUI already trusted? (mock.work was never trusted here; record trust state)
cj = json.load(open(os.path.join(mock.cfg, ".claude.json")))
R.save("claude-json-projects-trust.json", json.dumps({k: v.get("hasTrustDialogAccepted") for k, v in cj.get("projects", {}).items()}, indent=1))
run("permission_mode_bypass_control", fresh("bypass"), ["--permission-mode", "bypassPermissions"])
R.save("results.json", json.dumps(res, indent=1))
mock.close()
print(json.dumps(res, indent=1))
