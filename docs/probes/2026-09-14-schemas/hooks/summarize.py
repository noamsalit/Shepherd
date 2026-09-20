#!/usr/bin/env python3
"""Build the field matrix from every live capture (2026-09-14).

Re-run: python3 docs/probes/2026-09-14-schemas/hooks/summarize.py
Writes live/_field-matrix.txt and live/_sequences.txt. String values of free-text
fields (prompt, last_assistant_message, delta, message, tool_input, tool_response, ...)
are summarized by type/length only; enum-like fields list their distinct values.
"""
import collections, glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, "live")
ENUMISH = {"hook_event_name", "source", "reason", "error", "permission_mode", "notification_type", "trigger",
           "tool_name", "agent_type", "stop_hook_active", "final", "is_interrupt", "event", "load_reason",
           "memory_type", "expansion_type", "command_name", "mode", "action", "from_model", "to_model",
           "prompt_cache_likely_expired", "prompt_cache_warm", "cache_ttl", "pricing", "requested_model", "model",
           "custom_instructions", "index"}
events = collections.defaultdict(lambda: {"n": 0, "runs": set(), "keys": collections.Counter(), "vals": collections.defaultdict(collections.Counter), "types": collections.defaultdict(set)})
seq = []
bad = 0
for f in sorted(glob.glob(os.path.join(LIVE, "*", "events.jsonl"))):
    run = os.path.basename(os.path.dirname(f))
    for line in open(f):
        try:
            r = json.loads(line)
        except Exception:
            bad += 1
            continue
        p = r.get("payload")
        ev = (p or {}).get("hook_event_name") or r.get("_event")
        seq.append((run, r.get("_captured_at"), r.get("_event"), ev, (p or {}).get("session_id"), (p or {}).get("agent_id"), (p or {}).get("prompt_id")))
        if not isinstance(p, dict):
            continue
        e = events[ev]; e["n"] += 1; e["runs"].add(run)
        for k, v in p.items():
            e["keys"][k] += 1
            e["types"][k].add(type(v).__name__)
            if k in ENUMISH:
                e["vals"][k][json.dumps(v)[:80]] += 1
            elif k == "effort":
                e["vals"][k][json.dumps(v)] += 1
with open(os.path.join(LIVE, "_field-matrix.txt"), "w") as out:
    out.write(f"# built from {LIVE}/*/events.jsonl; unparseable lines: {bad}\n")
    for ev in sorted(events):
        e = events[ev]
        out.write(f"\n== {ev}  n={e['n']}  runs={sorted(e['runs'])}\n")
        for k, c in sorted(e["keys"].items()):
            pres = "always" if c == e["n"] else f"sometimes {c}/{e['n']}"
            vals = dict(e["vals"].get(k, {}))
            out.write(f"   {k:32s} {'/'.join(sorted(e['types'][k])):10s} {pres:18s} {vals if vals else ''}\n")
with open(os.path.join(LIVE, "_sequences.txt"), "w") as out:
    for s in seq:
        out.write("\t".join(str(x) for x in s) + "\n")
print("events:", {k: v["n"] for k, v in sorted(events.items())}, "bad lines:", bad)
