#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): session-ending and compaction signals in the TUI.
  compact   context_exhausted = PreCompact{trigger:auto} with no PostCompact before death (spec 966, 1087):
            (a) provoke auto-compaction (mock reports a near-full context window);
            (b) provoke it again, hang the summarisation request, and kill the session mid-compaction.
  resume    SessionEnd.reason = resume (spec 970): `/resume <other session id>` typed into a running TUI.
  logout    SessionEnd.reason = logout (spec 969): `/logout` typed into a TUI authenticated by a FAKE API key in an
            isolated CLAUDE_CONFIG_DIR (the real account is never involved).
Backend: mock_api2.py + isolated CLAUDE_CONFIG_DIR; the CLI is the real binary. All hooks captured.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_lifecycle_end.py [compact] [resume] [logout]
"""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

parts = [a for a in sys.argv[1:] if a in ("compact", "resume", "logout")] or ["compact", "resume", "logout"]
R = Run("lifecycle-end")
SOCK = "shp-gap-life"
assert tm(SOCK, "ls").returncode != 0
HL = R.path("hooks.jsonl")
BIG = 190000
COMPACT_MARK = os.environ.get("SHP_COMPACT_MARK", "CRITICAL: Respond with TEXT ONLY")   # first words of the summarisation request (seen in mock log)
rules = {"rules": [], "default_text": "OK-MOCK", "count_tokens": int(os.environ.get("SHP_COUNT_TOKENS", "10"))}
mock = MockEnv(R, "life", rules)
write_json(os.path.join(mock.work, ".claude", "settings.json"), settings_obj(HL, R.ver))
res = {}


def evs(n, keys=("source", "reason", "trigger", "notification_type", "error")):
    out = []
    for h in hooks(HL)[n:]:
        s = h["_event"]
        for k in keys:
            if h["payload"].get(k) is not None:
                s += f"[{k}={h['payload'][k]}]"
        s += f"@{h['payload'].get('session_id', '')[:8]}"
        out.append(s)
    return out


def set_rules(extra_first):
    r = dict(rules); r["rules"] = extra_first + rules["rules"]; mock.set_rules(r)


try:
    if "compact" in parts:
        cenv = [x for x in os.environ.get("SHP_COMPACT_ENV", "CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000,CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1").split(",") if x]
        R.log(f"compaction env: {cenv}")
        t = Tui(R, SOCK, "shepherd_compact", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list() + cenv)
        t.trust(); wait_event(HL, ev("SessionStart"), 30); time.sleep(3)
        # (a) one turn whose response claims ~190k input tokens, then another turn
        n = len(hooks(HL))
        set_rules([{"match": "FILL-1", "require_tools": True, "not_tool_result": True, "once": True, "input_tokens": BIG, "text": "FILLED"}])
        FILLER = int(os.environ.get("SHP_FILL_KB", "0"))
        if FILLER:
            t.paste("FILL-1 please. Context filler follows.\n" + ("lorem ipsum dolor sit amet " * (FILLER * 1024 // 27)), "compact-filler-1.txt")
            time.sleep(2); t.keys("Enter")
        else:
            t.submit("FILL-1 please")
        wait_event(HL, ev("Stop"), 30, after=n); time.sleep(2)
        t.save_screen("compact-a-after-fill.txt")
        t.submit("NEXT-1 after the big turn")
        wait_event(HL, ev("Stop"), 60, after=len(hooks(HL)) - 1)
        wait_event(HL, ev("PostCompact"), 30, after=n)
        time.sleep(3)
        t.save_screen("compact-a-after-next.txt")
        res["compact_a_auto"] = evs(n)
        R.log(f"compact_a: {res['compact_a_auto']}")
        if "--only-a" in sys.argv:
            raise SystemExit(0)
        # (b) fill again, then hang the summarisation request and kill the session while it is pending
        n = len(hooks(HL))
        set_rules([{"match": COMPACT_MARK, "hang_s": 300, "text": "<summary>never</summary>"},
                   {"match": "FILL-2", "require_tools": True, "not_tool_result": True, "once": True, "input_tokens": BIG, "text": "FILLED-2"}])
        if FILLER:
            t.paste("FILL-2 please. Context filler follows.\n" + ("lorem ipsum dolor sit amet " * (FILLER * 1024 // 27)), "compact-filler-2.txt")
            time.sleep(2); t.keys("Enter")
        else:
            t.submit("FILL-2 please")
        wait_event(HL, ev("Stop"), 30, after=n); time.sleep(2)
        t.submit("NEXT-2 after the second big turn")
        _, pc = wait_event(HL, ev("PreCompact"), 45, after=n)
        time.sleep(4)
        t.save_screen("compact-b-while-compacting.txt")
        cpid = claude_pid_under(t.pane_pid)
        t.kill()   # tmux kill-session: SIGHUP to the pane process
        time.sleep(5)
        res["compact_b_killed_mid_compaction"] = {"events": evs(n), "claude_alive_after_kill": bool(cpid and os.path.exists(f"/proc/{cpid}"))}
        R.log(f"compact_b: {res['compact_b_killed_mid_compaction']}")
        mock.set_rules(rules)

    if "resume" in parts:
        # a finished session to resume into
        other = subprocess.run(["claude", "-p", "--model", HAIKU, "--output-format", "json", "--", "OTHER session for resume"],
                               cwd=mock.work, env=mock.env_dict(), capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        other_id = json.loads(other.stdout)["session_id"]
        n = len(hooks(HL))
        t = Tui(R, SOCK, "shepherd_resume", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t.trust(5); wait_event(HL, ev("SessionStart", source="startup"), 30, after=n); time.sleep(3)
        t.submit("FIRST turn in the session that will be left")
        wait_event(HL, ev("Stop"), 30, after=n); time.sleep(2)
        t.submit(f"/resume {other_id}")
        _, se = wait_event(HL, ev("SessionEnd"), 30, after=n)
        wait_event(HL, lambda h: h["_event"] == "SessionStart" and h["payload"].get("source") == "resume", 20, after=n)
        time.sleep(3)
        t.save_screen("resume-screen.txt")
        res["resume"] = {"other_session_id": other_id, "events": evs(n)}
        R.log(f"resume: {res['resume']}")
        t.kill(); time.sleep(3)

    if "logout" in parts:
        n = len(hooks(HL))
        t = Tui(R, SOCK, "shepherd_logout", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t.trust(5); wait_event(HL, ev("SessionStart"), 30, after=n); time.sleep(3)
        t.submit("/logout")
        time.sleep(8)
        t.save_screen("logout-screen.txt")
        res["logout"] = {"events": evs(n), "pane": t.fmt("dead=#{pane_dead} status=#{pane_dead_status}")}
        R.log(f"logout: {res['logout']}")
        t.kill(); time.sleep(3)
finally:
    R.save("results.json", json.dumps(res, indent=1))
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(res, indent=1))
