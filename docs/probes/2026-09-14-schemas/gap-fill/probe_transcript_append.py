#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): is a Claude Code transcript append-only with whole lines, as
parse_transcript_delta(path, offset) assumes (spec 437)?
A poller watches every *.jsonl in the session's project dir every ~2 ms for the whole run and records
  * any change that is not a pure append (new content does not start with the previous content) -> violation
  * any observation where the file does not end with "\n" (a reader could see a partial trailing line)
while a TUI session goes through: a 400 KiB assistant message, a tool call with a large result, Write-tool edits
(file-history), /rename, manual /compact, /rewind (conversation + code restore), /clear, and `claude --resume`.
Backend: mock_api2.py + isolated CLAUDE_CONFIG_DIR. The CLI and the transcript writer are the real binary.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_transcript_append.py
"""
import glob, hashlib, json, os, threading, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("transcript-append")
SOCK = "shp-gap-tapp"
assert tm(SOCK, "ls").returncode != 0
HL = R.path("hooks.jsonl")
BIGTEXT = "BIGTEXT " + ("0123456789abcdef" * (400 * 1024 // 16))
rules = {"rules": [
    {"match": "APP-BIGTEXT", "require_tools": True, "not_tool_result": True, "once": True, "text": BIGTEXT},
    {"match": "APP-BIGTOOL", "require_tools": True, "not_tool_result": True, "once": True,
     "tool_use": {"name": "Bash", "input": {"command": "seq 1 200000", "description": "Print numbers"}}},
    {"match": "APP-WRITE1", "require_tools": True, "not_tool_result": True, "once": True,
     "tool_use": {"name": "Write", "input": {"file_path": "__WORK__/edited.txt", "content": "version one\n"}}},
    {"match": "APP-WRITE2", "require_tools": True, "not_tool_result": True, "once": True,
     "tool_use": {"name": "Write", "input": {"file_path": "__WORK__/edited.txt", "content": "version two\n"}}},
    {"match": "CRITICAL: Respond with TEXT ONLY", "text": "<summary>Probe summary for manual compact.</summary>"},
], "default_text": "OK-MOCK", "default_after_tool": "OK-AFTER-TOOL"}
mock = MockEnv(R, "tapp", {"rules": []})
rs = json.loads(json.dumps(rules).replace("__WORK__", mock.work))
mock.set_rules(rs)
write_json(os.path.join(mock.work, ".claude", "settings.json"),
           settings_obj(HL, R.ver, extra={"permissions": {"allow": ["Bash(seq:*)", f"Write({mock.work}/**)", "Write"]}}))
proj_glob = os.path.join(mock.cfg, "projects", "*", "*.jsonl")

state = {}          # path -> bytes last seen
obs = []            # observation log
stop = threading.Event()
phase = ["start"]


def poller():
    while not stop.is_set():
        for p in glob.glob(proj_glob):
            try:
                b = open(p, "rb").read()
            except FileNotFoundError:
                continue
            prev = state.get(p)
            if prev is not None and b == prev:
                continue
            rec = {"t": round(time.time(), 4), "phase": phase[0], "file": os.path.basename(p), "size": len(b),
                   "prev_size": None if prev is None else len(prev), "ends_with_newline": b.endswith(b"\n")}
            if prev is not None and not b.startswith(prev):
                i = next((k for k in range(min(len(b), len(prev))) if b[k] != prev[k]), min(len(b), len(prev)))
                rec["VIOLATION_not_append"] = {"first_diff_offset": i, "prev_len": len(prev), "new_len": len(b),
                                               "prev_line_at_diff": prev[prev.rfind(b"\n", 0, i) + 1: prev.find(b"\n", i)][:200].decode("utf-8", "replace"),
                                               "new_line_at_diff": b[b.rfind(b"\n", 0, i) + 1: b.find(b"\n", i)][:200].decode("utf-8", "replace")}
            if not rec["ends_with_newline"]:
                rec["partial_tail_bytes"] = len(b) - (b.rfind(b"\n") + 1)
            obs.append(rec)
            state[p] = b
        time.sleep(0.002)


def step(label, fn, wait=8):
    phase[0] = label
    R.log(f"STEP {label}")
    fn()
    time.sleep(wait)
    R.save(f"screen-{label}.txt", t.screen())


th = threading.Thread(target=poller, daemon=True); th.start()
t = Tui(R, SOCK, "shepherd_tapp", mock.work, ["claude", "--model", HAIKU], extra_env=mock.env_list())
res = {}
try:
    t.trust(); wait_event(HL, ev("SessionStart"), 30); time.sleep(3)
    step("turn_small", lambda: t.submit("hello small turn"), 5)
    step("big_assistant_text", lambda: t.submit("APP-BIGTEXT please"), 12)
    step("big_tool_result", lambda: t.submit("APP-BIGTOOL please"), 12)
    step("write_tool_1", lambda: t.submit("APP-WRITE1 please"), 8)
    step("write_tool_2", lambda: t.submit("APP-WRITE2 please"), 8)
    step("rename", lambda: t.submit("/rename probe-append-title"), 5)
    step("manual_compact", lambda: t.submit("/compact"), 15)
    step("after_compact_turn", lambda: t.submit("turn after compact"), 6)
    # /rewind: open the picker, go up one entry, Enter; then take the first restore option
    def rewind():
        t.submit("/rewind"); time.sleep(3); R.save("screen-rewind-picker.txt", t.screen())
        t.keys("Up"); time.sleep(1); R.save("screen-rewind-picker-up.txt", t.screen())
        t.keys("Enter"); time.sleep(3); R.save("screen-rewind-options.txt", t.screen())
        t.keys("Enter"); time.sleep(3)
    step("rewind", rewind, 6)
    step("after_rewind_turn", lambda: t.submit("turn after rewind"), 6)
    ids_before_clear = sorted(os.path.basename(p) for p in glob.glob(proj_glob))
    step("clear", lambda: t.submit("/clear"), 6)
    step("after_clear_turn", lambda: t.submit("turn after clear"), 6)
    first = [h for h in hooks(HL) if h["_event"] == "SessionStart"][0]["payload"]["session_id"]
    t.submit("/exit"); time.sleep(4)
    t2 = Tui(R, SOCK, "shepherd_tapp2", mock.work, ["claude", "--model", HAIKU, "--resume", first], extra_env=mock.env_list())
    phase[0] = "resume"; time.sleep(8)
    step("resume_turn", lambda: t2.submit("turn after resume"), 8)
    t2.submit("/exit"); time.sleep(4)
    stop.set(); th.join(2)
    viol = [o for o in obs if "VIOLATION_not_append" in o]
    partial = [o for o in obs if not o["ends_with_newline"]]
    res = {"observations": len(obs), "violations": len(viol), "partial_tail_observations": len(partial),
           "files": sorted(set(o["file"] for o in obs)), "ids_before_clear": ids_before_clear,
           "per_phase": {}}
    for o in obs:
        pp = res["per_phase"].setdefault(o["phase"], {"changes": 0, "violations": 0, "partial": 0, "files": set()})
        pp["changes"] += 1; pp["violations"] += "VIOLATION_not_append" in o; pp["partial"] += not o["ends_with_newline"]; pp["files"].add(o["file"])
    for v in res["per_phase"].values():
        v["files"] = sorted(v["files"])
    R.save("edited-file-final.txt", open(os.path.join(mock.work, "edited.txt")).read() if os.path.exists(os.path.join(mock.work, "edited.txt")) else "<absent>")
finally:
    stop.set()
    R.save("observations.jsonl", "".join(json.dumps(o) + "\n" for o in obs))
    R.save("results.json", json.dumps(res, indent=1, default=list))
    # line-type outline of each transcript (types only, no content)
    outl = {}
    for p in glob.glob(proj_glob):
        rows = []
        for line in open(p, "rb"):
            try:
                d = json.loads(line); rows.append(f"{d.get('type')}{'/' + d['subtype'] if d.get('subtype') else ''} len={len(line)}")
            except Exception:
                rows.append(f"UNPARSEABLE len={len(line)}")
        outl[os.path.basename(p)] = rows
    R.save("transcript-outline.json", json.dumps(outl, indent=1))
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(res, indent=1, default=list))
