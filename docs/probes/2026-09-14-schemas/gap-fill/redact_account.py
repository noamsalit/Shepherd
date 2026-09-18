#!/usr/bin/env python3
"""Replace the string values of any "account" object (email, organization, subscriptionType, apiProvider)
with "<redacted>" in the JSON / JSONL files given on the command line (in place). Gap-fill probe helper, 2026-09-14.
Usage: python3 redact_account.py <file>..."""
import json, sys
def walk(o):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k == "account" and isinstance(v, dict):
                o[k] = {kk: "<redacted>" for kk in v}
            elif k == "email" and isinstance(v, str):
                o[k] = "<redacted>"
            else:
                walk(v)
    elif isinstance(o, list):
        for x in o:
            walk(x)
for p in sys.argv[1:]:
    txt = open(p).read()
    if p.endswith(".jsonl"):
        out = []
        for line in txt.splitlines():
            try:
                o = json.loads(line); walk(o); out.append(json.dumps(o))
            except Exception:
                out.append(line)
        open(p, "w").write("\n".join(out) + "\n")
    else:
        o = json.loads(txt); walk(o); open(p, "w").write(json.dumps(o, indent=1))
    print("redacted", p)
