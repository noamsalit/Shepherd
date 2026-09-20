#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): Claude Code effort ladder (spec 552, 454, 498, 1656).
  1. `claude --help` text for --effort
  2. invalid values (--effort bogus, --effort MAX) -> exit code + stderr
  3. every documented level x {haiku, sonnet, opus} in -p against a LOCAL MOCK API, logging what the CLI puts in
     the Messages request (output_config / thinking / effort-like keys) and the hook payload's effort field.
No real API call is made: isolated CLAUDE_CONFIG_DIR, fake ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL=127.0.0.1 mock.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_effort.py
"""
import json, os, signal, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("effort")
help_txt = subprocess.run(["claude", "--help"], capture_output=True, text=True).stdout
R.save("claude-help.txt", help_txt)
d = mktmp("effort"); cfg = os.path.join(d, "cfg"); os.makedirs(cfg)
port = free_port(); reqlog = R.path("mock-requests.jsonl"); hooklog = R.path("hooks.jsonl")
rules = R.save("rules.json", json.dumps({"rules": [], "default_text": "OK-MOCK"}))
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_api2.py"), str(port), rules, reqlog], start_new_session=True)
time.sleep(0.8)
settings = write_json(os.path.join(d, "flag-settings.json"), settings_obj(hooklog, R.ver, events=["UserPromptSubmit", "Stop"]))
env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k.startswith("ANTHROPIC"))}
env.update({"CLAUDE_CONFIG_DIR": cfg, "ANTHROPIC_API_KEY": "sk-ant-api03-shp-fake-key-for-mock",
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}", "CLAUDE_CODE_MAX_RETRIES": "0",
            "DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1"})
results = []


def run(label, args):
    with open(reqlog, "a") as f:
        f.write(json.dumps({"marker": label}) + "\n")
    with open(hooklog, "a") as f:
        f.write(json.dumps({"_event": "MARKER", "label": label, "payload": {}}) + "\n")
    cmd = ["claude", "-p", "--settings", settings, "--output-format", "json"] + args + ["Say hi."]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = "timeout", "", ""
    res = None
    try:
        j = json.loads(out); res = {k: j.get(k) for k in ("subtype", "is_error", "result")}
    except Exception:
        res = out[:300]
    r = {"label": label, "argv": ["claude"] + cmd[1:], "rc": rc, "stdout_summary": res, "stderr": err.strip()[:500], "wall_s": round(time.time() - t0, 2)}
    results.append(r); R.log(json.dumps(r))


try:
    run("effort=bogus haiku", ["--model", HAIKU, "--effort", "bogus"])
    run("effort=MAX haiku (uppercase)", ["--model", HAIKU, "--effort", "MAX"])
    run("effort=bogus claude-sonnet-5", ["--model", "claude-sonnet-5", "--effort", "bogus"])
    run("effort=MAX claude-sonnet-5 (uppercase)", ["--model", "claude-sonnet-5", "--effort", "MAX"])
    run("effort=auto claude-sonnet-5", ["--model", "claude-sonnet-5", "--effort", "auto"])
    for model in (HAIKU, "claude-sonnet-5", "claude-opus-5"):
        run(f"no effort {model}", ["--model", model])
        for lvl in ("low", "medium", "high", "xhigh", "max"):
            run(f"effort={lvl} {model}", ["--model", model, "--effort", lvl])
finally:
    os.killpg(srv.pid, signal.SIGTERM)
R.save("runs.jsonl", "".join(json.dumps(r) + "\n" for r in results))
# summary table: label -> output_config/thinking/effort_like in the request, effort in UserPromptSubmit payload
summary, label = [], None
reqs = [json.loads(l) for l in open(reqlog)] if os.path.exists(reqlog) else []
hk = hooks(hooklog)
cur = None; hmap = {}
for h in hk:
    if h.get("_event") == "MARKER":
        cur = h["label"]
    elif h.get("_event") == "UserPromptSubmit":
        hmap.setdefault(cur, {})["UserPromptSubmit"] = h["payload"].get("effort", "<absent>")
    elif h.get("_event") == "Stop":
        hmap.setdefault(cur, {})["Stop"] = h["payload"].get("effort", "<absent>")
for q in reqs:
    if "marker" in q:
        label = q["marker"]; continue
    if q.get("method") == "POST" and q.get("tools"):   # the main-loop request (has tools)
        summary.append({"label": label, "model": q.get("model"), "output_config": q.get("output_config"), "thinking": q.get("thinking"),
                        "effort_like": q.get("effort_like"), "anthropic_beta": q.get("anthropic_beta"), "hook_effort": hmap.get(label, "<no hook>")})
R.save("summary.jsonl", "".join(json.dumps(s) + "\n" for s in summary))
print(open(R.path("summary.jsonl")).read())
