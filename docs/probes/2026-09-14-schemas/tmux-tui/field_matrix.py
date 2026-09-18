#!/usr/bin/env python3
"""Per-event field presence/type/values over one or more capture JSONL files.
Usage: field_matrix.py <hooks.jsonl>...   (string values longer than 60 chars are shown as <len N>)"""
import json, sys, collections
cnt = collections.Counter(); keys = collections.defaultdict(collections.Counter)
vals = collections.defaultdict(lambda: collections.defaultdict(set)); types = collections.defaultdict(lambda: collections.defaultdict(set))
for fn in sys.argv[1:]:
    for l in open(fn):
        h = json.loads(l); e = h["_event"]; p = h["payload"]; cnt[e] += 1
        for k, v in p.items():
            keys[e][k] += 1; types[e][k].add(type(v).__name__)
            s = v if isinstance(v, (bool, int, float)) or v is None else (v if isinstance(v, str) and len(v) <= 60 else f"<{type(v).__name__} len {len(v)}>")
            if isinstance(v, str) and len(v) <= 60 and k in ("session_id", "prompt_id", "tool_use_id", "agent_id", "turn_id", "message_id"):
                s = "<uuid>"
            if isinstance(v, str) and k in ("delta", "prompt", "last_assistant_message") and "\n" in v:
                s = f"<str len {len(v)} multiline>"
            if isinstance(v, str) and k in ("transcript_path", "cwd", "scratchpad_dir", "agent_transcript_path"):
                s = "<path>"
            vals[e][k].add(json.dumps(s) if not isinstance(s, str) else s)
for e in sorted(cnt):
    print(f"== {e}  (n={cnt[e]})")
    for k in keys[e]:
        pres = "always" if keys[e][k] == cnt[e] else f"sometimes {keys[e][k]}/{cnt[e]}"
        v = sorted(vals[e][k]); vs = ", ".join(v[:6]) + (" ..." if len(v) > 6 else "")
        print(f"  {k}: {'|'.join(sorted(types[e][k]))}; {pres}; {vs}")
