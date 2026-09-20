#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): raw key bytes into the Claude Code TUI through tmux (spec 1153, 1171-1173, 428).
The byte-level delivery is in probe_tmux_attach_keys.sh (keydump.py). This checks what the TUI does with them:
  * send-keys -H 1b 5b 41 (raw Up) at the idle prompt -> history recall?
  * paste-buffer -p of a two-line text (bracketed paste) -> one prompt with an embedded newline?
  * send-keys -H 03 (raw Ctrl-C) at the idle prompt, once
  * send-keys -H 1b (raw Esc) with text in the input box
Backend: mock_api2.py + isolated CLAUDE_CONFIG_DIR.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_keys_claude.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("keys-claude")
SOCK = "shp-gap-kc"
assert tm(SOCK, "ls").returncode != 0
HL = R.path("hooks.jsonl")
mock = MockEnv(R, "kc")
write_json(os.path.join(mock.work, ".claude", "settings.json"), settings_obj(HL, R.ver, events=["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"]))
t = Tui(R, SOCK, "shepherd_kc", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
res = {}
try:
    t.trust(); wait_event(HL, ev("SessionStart"), 30); time.sleep(3)
    n = len(hooks(HL)); t.submit("FIRST-PROMPT-FOR-HISTORY"); wait_event(HL, ev("Stop"), 20, after=n); time.sleep(2)
    tm(SOCK, "send-keys", "-t", t.t, "-H", "1b", "5b", "41", run=R); time.sleep(1.5)
    s = t.screen(); R.save("01-after-raw-up.txt", s)
    res["raw_up_recalls_history"] = ("History 1/1" in s) and ("❯ FIRST-PROMPT-FOR-HISTORY" in s)
    tm(SOCK, "send-keys", "-t", t.t, "C-u", run=R); time.sleep(0.5)   # clear the input line
    # also check whether C-u cleared it
    R.save("01b-after-ctrl-u.txt", t.screen())
    n = len(hooks(HL))
    t.paste("PASTE-LINE-ONE\nPASTE-LINE-TWO", "paste.txt"); time.sleep(1.5)
    R.save("02-after-bracketed-paste.txt", t.screen())
    t.keys("Enter")
    _, ups = wait_event(HL, ev("UserPromptSubmit"), 20, after=n)
    res["bracketed_paste_prompt"] = ups["payload"]["prompt"] if ups else None
    wait_event(HL, ev("Stop"), 20, after=n); time.sleep(2)
    tm(SOCK, "send-keys", "-t", t.t, "-H", "03", run=R); time.sleep(0.8)
    s = t.screen(); R.save("03-after-raw-ctrl-c-idle.txt", s)
    res["raw_ctrl_c_idle_screen_hint"] = [l.strip() for l in s.splitlines() if "Ctrl-C" in l or "ctrl+c" in l.lower()]
    res["alive_after_one_ctrl_c"] = t.fmt("#{pane_dead}") == "0"
    time.sleep(3)
    t.text("TYPED-THEN-ESC"); time.sleep(0.8)
    tm(SOCK, "send-keys", "-t", t.t, "-H", "1b", run=R); time.sleep(1.2)
    s = t.screen(); R.save("04-after-raw-esc-with-text.txt", s)
    res["esc_clears_input"] = "TYPED-THEN-ESC" not in s
    tm(SOCK, "send-keys", "-t", t.t, "-H", "1b", run=R); time.sleep(1.2)
    R.save("04b-after-second-esc.txt", t.screen())
finally:
    R.save("results.json", json.dumps(res, indent=1))
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(res, indent=1))
