#!/usr/bin/env python3
"""Print a byte-faithful excerpt of one captured hook payload (2026-09-14).

Usage: excerpt.py <events.jsonl> <EventName> [nth=1] [key=value ...] [--max N]
The payload text is sliced out of the raw capture line (never re-serialized). The only
change allowed is trimming: any JSON string literal longer than N characters (default 140)
is cut and ends in `..."`. Also usable as a module: excerpt(path, event, nth, filters, max).
"""
import json, re, sys

STR = re.compile(r'"((?:[^"\\]|\\.)*)"')


def trim(raw: str, n: int) -> str:
    def rep(m):
        s = m.group(1)
        if len(s) <= n:
            return m.group(0)
        cut = s[:n]
        # do not end inside an escape sequence
        k = len(cut) - len(cut.rstrip("\\"))
        if k % 2 == 1:
            cut = cut[:-1]
        mu = re.search(r"\\u[0-9a-fA-F]{0,3}$", cut)
        if mu:
            cut = cut[:mu.start()]
        return '"' + cut + '..."'
    return STR.sub(rep, raw)


def excerpt(path, event, nth=1, filters=None, n=140):
    filters = filters or {}
    seen = 0
    for line in open(path, encoding="utf8"):
        rec = json.loads(line)
        if rec.get("_event") != event:
            continue
        p = rec["payload"]
        if not all(str(p.get(k)) == v for k, v in filters.items()):
            continue
        seen += 1
        if seen == nth:
            raw = line[line.index('"payload":') + len('"payload":'):].rstrip("\n")
            assert raw.endswith("}")
            raw = raw[:-1]
            assert json.loads(raw) == p
            return trim(raw, n), rec
    raise SystemExit(f"no match: {path} {event} nth={nth} {filters}")


if __name__ == "__main__":
    args = sys.argv[1:]
    n = 140
    if "--max" in args:
        i = args.index("--max"); n = int(args[i + 1]); del args[i:i + 2]
    path, ev = args[0], args[1]
    nth = 1
    rest = args[2:]
    if rest and rest[0].isdigit():
        nth = int(rest[0]); rest = rest[1:]
    filt = dict(a.split("=", 1) for a in rest)
    text, rec = excerpt(path, ev, nth, filt, n)
    print(text)
