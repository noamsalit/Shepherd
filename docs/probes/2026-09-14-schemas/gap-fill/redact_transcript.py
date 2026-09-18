#!/usr/bin/env python3
"""Gap-fill helper (2026-09-14): reduce a transcript captured from a REAL-config session to what the probe needs.
user/assistant entries keep their envelope and message; every other entry type keeps only its top-level key names and
type/subtype. Attachment and system-reminder text (which can carry the user's global instructions and host details) is
dropped. Usage: redact_transcript.py <in.jsonl> <out.jsonl>"""
import json, sys
out = []
for line in open(sys.argv[1]):
    try:
        d = json.loads(line)
    except Exception:
        out.append(json.dumps({"UNPARSEABLE_len": len(line)})); continue
    if d.get("type") in ("user", "assistant"):
        m = d.get("message", {})
        c = m.get("content")
        if isinstance(c, list):
            keep = []
            for b in c:
                if b.get("type") == "text" and "<system-reminder>" in b.get("text", ""):
                    keep.append({"type": "text", "text": "<redacted: system-reminder block>"})
                else:
                    keep.append(b)
            m = dict(m, content=keep)
        elif isinstance(c, str) and "<system-reminder>" in c:
            m = dict(m, content="<redacted: system-reminder text>")
        d = dict(d, message=m)
        out.append(json.dumps(d))
    else:
        out.append(json.dumps({"type": d.get("type"), "subtype": d.get("subtype"), "_keys": sorted(d.keys()), "_redacted": "non user/assistant entry reduced to key names"}))
open(sys.argv[2], "w").write("\n".join(out) + "\n")
