#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): configuration scopes Shepherd relies on.
Part hot   (spec 925-927, 881): hooks written into a RUNNING session's settings (project-local file, then the
           user-scope settings.json of an isolated CLAUDE_CONFIG_DIR). Do they fire on the next turn? Is SessionStart
           ever emitted for that session? Does ConfigChange fire?
Part user  (spec 2230-2233, 440-441): user-scope hooks carrying "_shepherd_managed": true (on the hook entry and on
           the matcher group) -- do they load? An identical command in user AND project scope -- one run or two?
Part mcp   (spec 1431-1433, 1695, 1700-1707): `claude mcp add -s user` file shape; `mcp list`/`mcp get`; does a
           running session pick the server up; which permissions.allow spellings allow mcp__shepherd__ping in -p;
           the interactive permission prompt for an MCP tool; a session with an allow rule gets no prompt.
Isolation: every run uses CLAUDE_CONFIG_DIR=<mktemp>/cfg and a local mock Messages API (mock_api2.py), so the user's
~/.claude/settings.json and ~/.claude.json are never read for these settings and never written.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py [hot] [user] [mcp]
"""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

parts = [a for a in sys.argv[1:] if a in ("hot", "user", "mcp")] or ["hot", "user", "mcp"]
R = Run("config-scopes")
SOCK = "shp-gap-cfg"
assert tm(SOCK, "ls").returncode != 0
USER_SETTINGS_REAL = os.path.expanduser("~/.claude/settings.json")
R.save("real-user-settings-sha256-before.txt", sha(USER_SETTINGS_REAL) + "\n")
BASE = {"enabledPlugins": {"cc10x@cc10x": False}, "remoteControlAtStartup": False}
out = {}


def evnames(p):
    return [h["_event"] for h in hooks(p)]


def run_p(mock, cwd, prompt, extra_args=(), timeout=60):
    cmd = ["claude", "-p", "--model", HAIKU, "--output-format", "json"] + list(extra_args) + [prompt]
    p = subprocess.run(cmd, cwd=cwd, env=mock.env_dict(), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    try:
        j = json.loads(p.stdout); s = {k: j.get(k) for k in ("subtype", "is_error", "result", "permission_denials")}
    except Exception:
        s = p.stdout[:400]
    return {"rc": p.returncode, "result": s, "stderr": p.stderr.strip()[:400]}


try:
    # ------------------------------------------------------------------------------------------------ hot
    if "hot" in parts:
        mock = MockEnv(R, "hot")
        write_json(os.path.join(mock.work, ".claude", "settings.json"), BASE)
        L_LOCAL, L_USER = R.path("hot-local-hooks.jsonl"), R.path("hot-user-hooks.jsonl")
        t = Tui(R, SOCK, "shepherd_hot", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t.trust(); time.sleep(4)
        t.submit("HOT-1 no hooks installed yet"); t.wait_screen("OK-MOCK", 20); time.sleep(2)
        # install hooks into the project-local file while the session runs
        s = settings_obj(L_LOCAL, R.ver, marker=True); s.pop("enabledPlugins"); s.pop("remoteControlAtStartup")
        write_json(os.path.join(mock.work, ".claude", "settings.local.json"), s)
        shutil.copy(os.path.join(mock.work, ".claude", "settings.local.json"), R.path("hot-settings.local.json"))
        R.log("wrote settings.local.json with hooks (running session)")
        time.sleep(5)
        after_write_local = evnames(L_LOCAL)
        t.submit("HOT-2 after local hooks were written")
        wait_event(L_LOCAL, ev("Stop"), 30)
        time.sleep(2)
        after_turn2_local = evnames(L_LOCAL)
        # install hooks into the user-scope settings.json of the isolated config dir
        su = settings_obj(L_USER, R.ver, marker=True); su.pop("remoteControlAtStartup")
        write_json(os.path.join(mock.cfg, "settings.json"), su)
        shutil.copy(os.path.join(mock.cfg, "settings.json"), R.path("hot-user-settings.json"))
        R.log("wrote CLAUDE_CONFIG_DIR/settings.json with hooks (running session)")
        time.sleep(5)
        n_local = len(hooks(L_LOCAL))
        after_write_user = evnames(L_USER)
        t.submit("HOT-3 after user-scope hooks were written")
        wait_event(L_LOCAL, ev("Stop"), 30, after=n_local)
        time.sleep(2)
        t.submit("/exit"); time.sleep(5)
        out["hot"] = {"local_events_right_after_write": after_write_local, "local_events_after_turn2": after_turn2_local,
                      "user_events_right_after_write": after_write_user,
                      "local_events_all": evnames(L_LOCAL), "user_events_all": evnames(L_USER),
                      "pane": t.fmt("dead=#{pane_dead} status=#{pane_dead_status}")}
        R.save("hot-screen-end.txt", t.screen())
        R.log(f"hot: {json.dumps(out['hot'])}")
        mock.close()

    # ------------------------------------------------------------------------------------------------ user
    if "user" in parts:
        mock = MockEnv(R, "user")
        DUP = R.path("user-dup-hooks.jsonl"); UONLY = R.path("user-only-hooks.jsonl"); PONLY = R.path("user-projonly-hooks.jsonl")
        def cmd(ev_, log):
            return f"SHP_CLAUDE_VERSION='{R.ver}' {CAP} {ev_} {log}"
        user_s = dict(BASE, hooks={e: [{"_shepherd_managed": True, "hooks": [
            {"type": "command", "command": cmd(e, DUP), "timeout": 10, "_shepherd_managed": True},
            {"type": "command", "command": cmd(e, UONLY), "timeout": 10, "_shepherd_managed": True}]}]
            for e in ("SessionStart", "UserPromptSubmit", "Stop")})
        proj_s = dict(BASE, hooks={e: [{"hooks": [
            {"type": "command", "command": cmd(e, DUP), "timeout": 10},
            {"type": "command", "command": cmd(e, PONLY), "timeout": 10}]}]
            for e in ("SessionStart", "UserPromptSubmit", "Stop")})
        write_json(os.path.join(mock.cfg, "settings.json"), user_s)
        write_json(os.path.join(mock.work, ".claude", "settings.json"), proj_s)
        shutil.copy(os.path.join(mock.cfg, "settings.json"), R.path("user-user-settings.json"))
        shutil.copy(os.path.join(mock.work, ".claude", "settings.json"), R.path("user-project-settings.json"))
        dbg = R.path("user-debug.log")
        r = run_p(mock, mock.work, "Say hi.", ["--debug-file", dbg])
        # same identical command, same timeout, but in user + local (not project)
        out["user"] = {"run": r, "dup_events": evnames(DUP), "user_only_events": evnames(UONLY), "project_only_events": evnames(PONLY)}
        with open(dbg) as f:
            out["user"]["debug_lines_matching"] = [l.strip()[:300] for l in f if any(k in l for k in ("_shepherd_managed", "nvalid", "hook", "Hook"))][:40]
        out["user"]["user_settings_after_run_unchanged"] = open(os.path.join(mock.cfg, "settings.json")).read() == open(R.path("user-user-settings.json")).read()
        R.log(f"user: {json.dumps(out['user'])[:1500]}")
        mock.close()

    # ------------------------------------------------------------------------------------------------ mcp
    if "mcp" in parts:
        MLOG = R.path("mcp-stub-messages.jsonl")
        rules = {"rules": [
            {"match": "MCP-PING", "match_body": "mcp__shepherd__ping", "require_tools": True, "not_tool_result": True,
             "tool_use": {"name": "mcp__shepherd__ping", "input": {}}},
        ], "default_text": "OK-MOCK", "default_after_tool": "OK-AFTER-TOOL"}
        mock = MockEnv(R, "mcp", rules)
        write_json(os.path.join(mock.work, ".claude", "settings.json"), dict(BASE, hooks=settings_obj(R.path("mcp-hooks.jsonl"), R.ver)["hooks"]))
        # S1 starts BEFORE the server is added
        t1 = Tui(R, SOCK, "shepherd_mcp1", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t1.trust(); time.sleep(5)
        env = mock.env_dict(); env["SHP_MCP_LOG"] = MLOG
        add_argv = ["claude", "mcp", "add", "-s", "user", "shepherd", "--", sys.executable, os.path.join(HERE, "mcp_stub.py"), MLOG]
        add = subprocess.run(add_argv, cwd=mock.work, env=env, capture_output=True, text=True, timeout=60)
        R.save("mcp-add.txt", f"$ {' '.join(add_argv)}\nrc={add.returncode}\nstdout:\n{add.stdout}\nstderr:\n{add.stderr}\n")
        cj = json.load(open(os.path.join(mock.cfg, ".claude.json")))
        R.save("mcp-claude-json-after-add.json", json.dumps({"top_level_keys": sorted(cj.keys()), "mcpServers": cj.get("mcpServers"),
                                                              "projects_keys": {k: sorted(v.keys()) for k, v in cj.get("projects", {}).items()}}, indent=1))
        lst = subprocess.run(["claude", "mcp", "list"], cwd=mock.work, env=env, capture_output=True, text=True, timeout=90)
        get = subprocess.run(["claude", "mcp", "get", "shepherd"], cwd=mock.work, env=env, capture_output=True, text=True, timeout=90)
        R.save("mcp-list-get.txt", f"$ claude mcp list\nrc={lst.returncode}\n{lst.stdout}{lst.stderr}\n$ claude mcp get shepherd\nrc={get.returncode}\n{get.stdout}{get.stderr}\n")
        # S1 (already running) is asked to call the tool
        nreq = len(mock.requests())
        t1.submit("MCP-PING please call the shepherd ping tool"); time.sleep(12)
        s1_reqs = [q for q in mock.requests()[nreq:] if q.get("tools")]
        R.save("mcp-s1-screen.txt", t1.screen())
        out["mcp_s1_running_before_add"] = {"main_requests": len(s1_reqs),
                                            "tools_had_mcp_shepherd": [any(x.startswith("mcp__shepherd") for x in q["tools"]) for q in s1_reqs]}
        t1.kill()
        # permission rule spellings in -p
        perm = {}
        for label, allow in (("none", []), ("server", ["mcp__shepherd"]), ("wildcard", ["mcp__shepherd__*"]), ("exact", ["mcp__shepherd__ping"])):
            d = os.path.join(mock.root, f"p_{label}"); os.makedirs(os.path.join(d, ".claude"))
            write_json(os.path.join(d, ".claude", "settings.json"), dict(BASE, permissions={"allow": allow}))
            nm = len(hooks(MLOG)) if os.path.exists(MLOG) else 0
            r = run_p(mock, d, "MCP-PING call the tool")
            calls = [m for m in hooks(MLOG)[nm:] if (m.get("msg") or {}).get("method") == "tools/call"]
            perm[label] = {"allow": allow, "rc": r["rc"], "result": r["result"], "stub_tools_call_count": len(calls)}
        out["mcp_permission_rules_p"] = perm
        R.log(f"mcp perms: {json.dumps(perm)[:1500]}")
        # S2 starts AFTER the add, no allow rule: interactive prompt path
        HL2 = R.path("mcp-hooks.jsonl")
        n2 = len(hooks(HL2))
        t2 = Tui(R, SOCK, "shepherd_mcp2", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        time.sleep(6)
        t2.submit("MCP-PING please call the shepherd ping tool")
        _, pr = wait_event(HL2, ev("PermissionRequest"), 30, after=n2)
        time.sleep(2)
        R.save("mcp-s2-permission-screen.txt", t2.screen())
        _, nt = wait_event(HL2, ev("Notification", notification_type="permission_prompt"), 15, after=n2)
        t2.keys("Enter")   # default option (Yes)
        time.sleep(6)
        R.save("mcp-s2-after-approve-screen.txt", t2.screen())
        out["mcp_s2_started_after_add"] = {"events": [h["_event"] + (f"({h['payload'].get('tool_name')})" if h['payload'].get('tool_name') else "") + (f"[{h['payload'].get('notification_type')}]" if h['payload'].get('notification_type') else "") for h in hooks(HL2)[n2:]]}
        t2.kill()
        # S3 with allow rule mcp__shepherd__* in project settings: no prompt expected
        d3 = os.path.join(mock.root, "s3"); os.makedirs(os.path.join(d3, ".claude"))
        HL3 = R.path("mcp-s3-hooks.jsonl")
        write_json(os.path.join(d3, ".claude", "settings.json"), dict(BASE, permissions={"allow": ["mcp__shepherd__*"]},
                                                                      hooks=settings_obj(HL3, R.ver)["hooks"]))
        t3 = Tui(R, SOCK, "shepherd_mcp3", d3, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t3.trust(); time.sleep(6)
        t3.submit("MCP-PING please call the shepherd ping tool")
        wait_event(HL3, ev("Stop"), 30)
        time.sleep(2)
        R.save("mcp-s3-screen.txt", t3.screen())
        out["mcp_s3_allow_wildcard"] = {"events": [h["_event"] + (f"({h['payload'].get('tool_name')})" if h['payload'].get('tool_name') else "") for h in hooks(HL3)]}
        t3.kill()
        mock.close()
finally:
    R.save("results.json", json.dumps(out, indent=1))
    R.save("real-user-settings-sha256-after.txt", sha(USER_SETTINGS_REAL) + "\n")
    tm(SOCK, "kill-server", run=R)
print(json.dumps(out, indent=1)[:8000])
