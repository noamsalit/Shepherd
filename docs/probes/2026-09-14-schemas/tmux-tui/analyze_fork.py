#!/usr/bin/env python3
"""Compare an original transcript with its --fork-session copy. Prints structure only
(entry types, uuid overlap, where the original id appears); no message content.
Usage: analyze_fork.py <original.jsonl> <fork.jsonl>"""
import json, sys, collections
o = [json.loads(l) for l in open(sys.argv[1])]
f = [json.loads(l) for l in open(sys.argv[2])]
oid = next(x["sessionId"] for x in o if x.get("sessionId"))
fid = next(x["sessionId"] for x in f if x.get("sessionId"))
ou = {x.get("uuid") for x in o if x.get("uuid")}
fu = [x.get("uuid") for x in f if x.get("uuid")]
print("original lines", len(o), "fork lines", len(f))
print("original id", oid, "fork id", fid)
print("fork entries whose uuid also exists in original:", sum(1 for u in fu if u in ou), "of", len(fu))
print("fork lines containing the original session id string:", sum(1 for l in open(sys.argv[2]) if oid in l))
print("fork sessionId values:", dict(collections.Counter(str(x.get("sessionId")) for x in f)))
print("original types:", dict(collections.Counter((x.get("type"), x.get("subtype")) for x in o)))
print("fork types:", dict(collections.Counter((x.get("type"), x.get("subtype")) for x in f)))
print("keys present in fork entries but never in original:", sorted({k for x in f for k in x} - {k for x in o for k in x}))
cb = [i for i, x in enumerate(o) if x.get("subtype") == "compact_boundary"]
print("original compact_boundary line indexes:", cb)
print("fork compact_boundary line indexes:", [i for i, x in enumerate(f) if x.get("subtype") == "compact_boundary"])

def paths(obj, needle, pre=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from paths(v, needle, f"{pre}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from paths(v, needle, f"{pre}[]")
    elif isinstance(obj, str) and needle in obj:
        yield pre
print("JSON paths in fork entries whose string value contains the original id:",
      dict(collections.Counter(p for x in f for p in paths(x, oid))))
print("fork entries carrying both keys -> (type, subtype, session_id is original?, sessionId is fork?):",
      dict(collections.Counter((x.get("type"), x.get("subtype"), x.get("session_id") == oid, x.get("sessionId") == fid)
                               for x in f if "session_id" in x)))
print("original entries with session_id key:", sum(1 for x in o if "session_id" in x),
      "all equal to original id:", all(x["session_id"] == oid for x in o if "session_id" in x))
