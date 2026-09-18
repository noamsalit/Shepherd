#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): explicit interrupt of a running TUI turn (spec 1169, 1231, 1975, 429, 965, 1181).
How is an interrupt delivered (Esc via send-keys, C-c via send-keys, SIGINT to the claude pid) and what hook /
transcript evidence does it leave (Stop? PostToolUseFailure.is_interrupt? "[Request interrupted by user]")?

Backend: local mock Messages API (mock_api2.py) with an isolated CLAUDE_CONFIG_DIR, so turns are deterministic:
the model "calls" Bash `sleep 30` (or the API response hangs) and we interrupt mid-turn. The CLI, its hooks and its
transcript are the real Claude Code binary. A final `--real` pass repeats the Esc-during-tool case against the real
API with haiku (the user's login, throwaway dir) to confirm the mock did not change the shape.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py [--real]
"""
import json, os, shutil, signal, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

REAL = "--real" in sys.argv
R = Run("interrupt-real" if REAL else "interrupt")
SOCK = "shp-gap-int"
assert tm(SOCK, "ls").returncode != 0, "probe socket busy"
HLOG = R.path("hooks.jsonl")
SLEEP_TOOL = {"name": "Bash", "input": {"command": "sleep 30", "description": "Sleep 30 seconds"}}
rules = {"rules": [
    {"match": "INT-ESC-TOOL", "not_tool_result": True, "require_tools": True, "once": True, "tool_use": SLEEP_TOOL},
    {"match": "INT-CC-TOOL", "not_tool_result": True, "require_tools": True, "once": True, "tool_use": SLEEP_TOOL},
    {"match": "INT-SIGINT-TOOL", "not_tool_result": True, "require_tools": True, "once": True, "tool_use": SLEEP_TOOL},
    {"match": "INT-ESC-STREAM", "not_tool_result": True, "require_tools": True, "once": True, "hang_s": 25, "text": "LATE-TEXT"},
], "default_text": "OK-MOCK"}

if REAL:
    work = mktmp("int-real"); mock = None; extra_env = []
else:
    mock = MockEnv(R, "int", rules); work = mock.work; extra_env = mock.env_list()
settings = settings_obj(HLOG, R.ver, extra={"permissions": {"allow": ["Bash(sleep:*)", "Bash(python3:*)"]}})
write_json(os.path.join(work, ".claude", "settings.json"), settings)
shutil.copy(os.path.join(work, ".claude", "settings.json"), R.path("project-settings.json"))

marks = []


def mark(label):
    n = len(hooks(HLOG)); marks.append({"label": label, "hook_index": n, "t": time.time()})
    R.log(f"MARK {label} hook_index={n}")
    return n


def events_since(n):
    return [h["_event"] + (f"({h['payload'].get('tool_name')})" if h["payload"].get("tool_name") else "")
            for h in hooks(HLOG)[n:]]


tui = Tui(R, SOCK, "shepherd_int", work, ["claude", "--model", HAIKU], extra_env=extra_env)
results = {}
try:
    tui.trust()
    i, ss = wait_event(HLOG, ev("SessionStart"), 40)
    tpath = ss["payload"]["transcript_path"] if ss else None
    cpid = claude_pid_under(tui.pane_pid)
    R.save("ids.txt", f"pane_pid={tui.pane_pid}\nclaude_pid={cpid}\ntranscript={tpath}\n")
    time.sleep(2)

    def tool_case(label, prompt, how):
        n = mark(label)
        size0 = transcript_state(tpath).get("size", 0)
        tui.submit(prompt)
        _, pre = wait_event(HLOG, ev("PreToolUse", tool_name="Bash"), 60, after=n)
        time.sleep(2.5)
        tui.save_screen(f"{label}-screen-running.txt")
        t_int = time.time()
        if how == "esc":
            tui.keys("Escape")
        elif how == "cc":
            tui.keys("C-c")
        elif how == "sigint":
            os.kill(cpid, signal.SIGINT)
        R.log(f"{label}: interrupt sent via {how}; PreToolUse seen={pre is not None}")
        time.sleep(8)
        tui.save_screen(f"{label}-screen-after.txt")
        evs = events_since(n)
        b = open(tpath, "rb").read() if tpath and os.path.exists(tpath) else b""
        R.save(f"{label}-transcript-delta.jsonl", b[size0:].decode("utf-8", "replace"))
        alive = os.path.exists(f"/proc/{cpid}")
        results[label] = {"how": how, "events": evs, "claude_alive": alive, "pane_dead": tui.fmt("#{pane_dead}")}
        R.log(f"{label}: {results[label]}")
        # does the session still take a prompt?
        n2 = mark(label + "-after")
        tui.submit("Reply with only the word AFTER")
        _, st = wait_event(HLOG, ev("Stop"), 40, after=n2)
        results[label]["next_turn_stop"] = st is not None
        time.sleep(1)

    if REAL:
        tool_case("esc_tool", "Use the Bash tool (foreground, run_in_background false) to run exactly this command: python3 -c 'import time; time.sleep(40)'   Then reply DONE.", "esc")
    else:
        tool_case("esc_tool", "INT-ESC-TOOL", "esc")
        tool_case("cc_tool", "INT-CC-TOOL", "cc")
        # Esc while the API request is in flight (no tool yet)
        n = mark("esc_stream"); size0 = transcript_state(tpath).get("size", 0)
        tui.submit("INT-ESC-STREAM")
        wait_event(HLOG, ev("UserPromptSubmit"), 20, after=n)
        time.sleep(3); tui.save_screen("esc_stream-screen-running.txt")
        tui.keys("Escape"); time.sleep(6)
        tui.save_screen("esc_stream-screen-after.txt")
        b = open(tpath, "rb").read()
        R.save("esc_stream-transcript-delta.jsonl", b[size0:].decode("utf-8", "replace"))
        results["esc_stream"] = {"how": "esc", "events": events_since(n), "claude_alive": os.path.exists(f"/proc/{cpid}")}
        R.log(f"esc_stream: {results['esc_stream']}")
        n2 = mark("esc_stream-after"); tui.submit("Reply with only the word AFTER")
        results["esc_stream"]["next_turn_stop"] = wait_event(HLOG, ev("Stop"), 40, after=n2)[1] is not None
        time.sleep(1)
        # C-c at the idle prompt (send-keys), once
        n = mark("cc_idle"); tui.keys("C-c"); time.sleep(1.5)
        tui.save_screen("cc_idle-screen-after-first.txt")
        results["cc_idle"] = {"events": events_since(n), "claude_alive": os.path.exists(f"/proc/{cpid}")}
        time.sleep(3)
        # SIGINT to the claude pid during a tool call (last: it ends the session)
        tool_case("sigint_tool", "INT-SIGINT-TOOL", "sigint")
        results["sigint_tool"]["pane"] = tui.fmt("dead=#{pane_dead} status=#{pane_dead_status} signal=#{pane_dead_signal}")
        # SIGINT at the idle prompt, in a second session
        tui2 = Tui(R, SOCK, "shepherd_int2", work, ["claude", "--model", HAIKU], extra_env=extra_env)
        n = mark("sigint_idle")
        wait_event(HLOG, ev("SessionStart"), 40, after=n)
        time.sleep(3)
        cpid2 = claude_pid_under(tui2.pane_pid)
        os.kill(cpid2, signal.SIGINT); time.sleep(3)
        tui2.save_screen("sigint_idle-screen-after.txt")
        results["sigint_idle"] = {"events": events_since(n), "claude_alive": os.path.exists(f"/proc/{cpid2}"),
                                  "pane": tui2.fmt("dead=#{pane_dead} status=#{pane_dead_status} signal=#{pane_dead_signal}")}
        R.log(f"sigint_idle: {results['sigint_idle']}")
    if tpath and os.path.exists(tpath):
        shutil.copy(tpath, R.path("transcript-full.jsonl"))
    if REAL:   # real-config transcripts can carry the user's global instructions: keep a reduced copy only
        for name in ("transcript-full.jsonl", "esc_tool-transcript-delta.jsonl"):
            src = R.path(name)
            if os.path.exists(src):
                subprocess.run([sys.executable, os.path.join(HERE, "redact_transcript.py"), src, src.replace(".jsonl", "-redacted.jsonl").replace("-full-redacted", "-redacted")])
                os.remove(src)
finally:
    R.save("results.json", json.dumps({"results": results, "marks": marks}, indent=1))
    tm(SOCK, "kill-server", run=R)
    if mock:
        mock.close()
print(json.dumps(results, indent=1))
