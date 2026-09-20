#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): spawning an owned session with its brief as argv (spec 435, 1377, 2112).
  * tmux new-session with argv words (no shell) vs one command string (tmux runs it via sh -c)
  * does a positional prompt to interactive `claude` auto-submit (UserPromptSubmit), before or after the trust dialog?
  * do shell metacharacters, quotes, tabs, newlines and non-ASCII survive byte-for-byte?
  * a brief that starts with '-', with and without `--`
  * large briefs (20 KiB, 140 KiB) through tmux + execve
Backend: local mock Messages API + isolated CLAUDE_CONFIG_DIR (mock_api2.py); the CLI is the real binary.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_argv.py
"""
import json, os, shlex, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("argv")
SOCK = "shp-gap-argv"
assert tm(SOCK, "ls").returncode != 0
mock = MockEnv(R, "argv")
BRIEF = "ARGV-BRIEF $(echo EXPANDED) `echo BACKTICK` ; echo SEMI && 'single' \"double\" \\back $HOME *\nsecond line\tTAB ✓ end"
R.save("brief.txt", BRIEF)
results = {}


def case(label, argv_builder, trust=True, wait_s=25):
    d = os.path.join(mock.root, label); os.makedirs(os.path.join(d, ".claude"))
    hl = R.path(f"{label}-hooks.jsonl")
    write_json(os.path.join(d, ".claude", "settings.json"), settings_obj(hl, R.ver, events=["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"]))
    argv = argv_builder()
    try:
        t = Tui(R, SOCK, f"shepherd_{label}", d, argv, extra_env=mock.env_list())
    except OSError as e:
        results[label] = {"tmux_argv_words": len(argv), "longest_arg_bytes": max(len(a.encode()) for a in argv),
                          "spawn_error": f"OSError errno={e.errno}: {e.strerror} (execve of env/tmux)"}
        R.log(f"{label}: {results[label]}")
        return
    time.sleep(3)
    pp = t.pane_pid
    info = {"tmux_argv_words": len(argv), "pane_pid": pp}
    try:
        info["pane_comm"] = open(f"/proc/{pp}/comm").read().strip()
        info["pane_cmdline"] = open(f"/proc/{pp}/cmdline", "rb").read().split(b"\0")[:-1]
        info["pane_cmdline"] = [x.decode("utf-8", "replace") for x in info["pane_cmdline"]]
    except Exception as e:
        info["pane_proc_error"] = repr(e)
    cp = claude_pid_under(pp)
    if cp and cp != pp:
        info["claude_pid"] = cp
        info["claude_cmdline"] = [x.decode("utf-8", "replace") for x in open(f"/proc/{cp}/cmdline", "rb").read().split(b"\0")[:-1]]
    scr = t.screen()
    info["trust_dialog_shown"] = "trust this folder" in scr
    info["hooks_before_trust"] = [h["_event"] for h in hooks(hl)]
    R.save(f"{label}-screen-start.txt", scr)
    if trust and info["trust_dialog_shown"]:
        t.trust()
    _, ups = wait_event(hl, ev("UserPromptSubmit"), wait_s)
    _, stop = wait_event(hl, ev("Stop"), 10)
    info["events"] = [h["_event"] for h in hooks(hl)]
    if ups:
        p = ups["payload"]["prompt"]
        info["prompt_len"] = len(p)
        info["prompt_equals_brief"] = (p == BRIEF) if label.startswith(("a_", "b_", "c_")) else None
        info["prompt_head"] = p[:160]
    R.save(f"{label}-screen-end.txt", t.screen())
    info["pane_dead"] = t.fmt("dead=#{pane_dead} status=#{pane_dead_status}")
    results[label] = info
    R.log(f"{label}: {json.dumps(info)[:600]}")
    t.kill()


CL = ["claude", "--model", HAIKU]
try:
    case("a_argv_words", lambda: CL + [BRIEF])
    case("b_single_string_naive", lambda: [" ".join(CL) + " \"" + BRIEF + "\""])
    case("c_single_string_shlex", lambda: [" ".join(CL) + " " + shlex.quote(BRIEF)])
    case("d_dash_brief_no_separator", lambda: CL + ["-starts with a dash DASH-BRIEF"])
    case("e_dash_brief_with_separator", lambda: CL + ["--", "-starts with a dash DASH-BRIEF"])
    case("f_brief_20KiB", lambda: CL + ["BIG20 " + "x" * (20 * 1024)])
    case("g_brief_140KiB", lambda: CL + ["BIG140 " + "y" * (140 * 1024)], wait_s=15)
    case("h_brief_100KiB", lambda: CL + ["BIG100 " + "z" * (100 * 1024)], wait_s=20)
finally:
    R.save("results.json", json.dumps(results, indent=1))
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(results, indent=1)[:6000])
