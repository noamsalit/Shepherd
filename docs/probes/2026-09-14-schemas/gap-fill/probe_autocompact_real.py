#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): try to provoke AUTO compaction cheaply against the real API (haiku, the user's
login, throwaway cwd, project-settings hooks, cc10x disabled) using the env overrides found in the 2.1.270 binary.
Variants (each a fresh TUI session): CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=<pct>; CLAUDE_CODE_AUTO_COMPACT_WINDOW=<tokens>.
Each variant: two short turns, then look for PreCompact/PostCompact{trigger=auto}. Stops at the first variant that compacts.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_autocompact_real.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("autocompact-real")
SOCK = "shp-gap-acr"
assert tm(SOCK, "ls").returncode != 0
HL = R.path("hooks.jsonl")
work = mktmp("acr")
write_json(os.path.join(work, ".claude", "settings.json"), settings_obj(HL, R.ver))
VARIANTS = [("pct1", ["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1"]),
            ("window100k_pct1", ["CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1"])]
res = {}
try:
    for i, (label, envv) in enumerate(VARIANTS):
        n = len(hooks(HL))
        t = Tui(R, SOCK, f"shepherd_acr{i}", work, ["claude", "--model", HAIKU], extra_env=envv)
        if i == 0:
            t.trust()
        wait_event(HL, ev("SessionStart"), 40, after=n); time.sleep(3)
        for k, prompt in enumerate(("Reply with only the word ONE", "Reply with only the word TWO", "Reply with only the word THREE")):
            m = len(hooks(HL))
            t.submit(prompt)
            wait_event(HL, ev("Stop"), 90, after=m)
            _, pc = wait_event(HL, ev("PostCompact"), 5, after=n)
            time.sleep(2)
            R.save(f"{label}-screen-after-turn{k+1}.txt", t.screen())
            if pc:
                break
        evl = []
        for h in hooks(HL)[n:]:
            p = h["payload"]; s = h["_event"]
            for key in ("trigger", "source", "reason"):
                if p.get(key):
                    s += f"[{key}={p[key]}]"
            evl.append(s)
        res[label] = {"env": envv, "events": evl}
        R.log(f"{label}: {json.dumps(res[label])}")
        t.kill(); time.sleep(3)
        if any(e.startswith("PostCompact") or e.startswith("PreCompact") for e in evl):
            break
finally:
    R.save("results.json", json.dumps(res, indent=1))
    tm(SOCK, "kill-server", run=R)
print(json.dumps(res, indent=1))
