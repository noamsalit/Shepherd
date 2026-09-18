"""Field-presence matrix over every CLI stdout object captured by the agent-sdk-mcp probes.
Re-run: python3 summarize.py   -> captures/_field-matrix.txt
For each (type, subtype) and for nested message/result objects: how many objects, which keys appear in
how many of them, the JSON types seen, and up to 6 distinct short scalar values (strings >40 chars and
all *_id/uuid/signature/text fields are shown as <varies>)."""
import collections, json, pathlib
HERE = pathlib.Path(__file__).parent; CAP = HERE / "captures"
objs = []  # (source, obj)
for f in sorted(CAP.glob("*/raw-stream.jsonl")):
    for l in f.read_text().splitlines():
        o = json.loads(l)
        if o["_dir"] == "in":
            objs.append((f.parent.name, o["line"]))
for l in (CAP / "stdio-mcp/stream.jsonl").read_text().splitlines():
    objs.append(("stdio-mcp(cli -p)", json.loads(l)))
groups = collections.defaultdict(list)
for src, o in objs:
    t = o.get("type")
    st = o.get("subtype")
    if t == "control_request":
        st = o["request"].get("subtype")
    if t == "control_response":
        st = "(response)"
    groups[(t, st)].append((src, o))
    if t in ("assistant", "user") and isinstance(o.get("message"), dict):
        groups[(t + ".message", None)].append((src, o["message"]))
        if isinstance(o["message"].get("content"), list):
            for b in o["message"]["content"]:
                groups[(t + ".content[]", b.get("type"))].append((src, b))
VARY = ("id", "uuid", "signature", "text", "thinking", "session_id", "request_id", "tool_use_id", "timestamp", "cwd", "transcript_path", "content", "result", "prompt_id", "requestId", "message_id", "leafUuid", "parentUuid")
out = []
for key in sorted(groups, key=lambda k: (str(k[0]), str(k[1]))):
    items = groups[key]
    srcs = sorted({s for s, _ in items})
    out.append(f"== type={key[0]} subtype={key[1]}  n={len(items)}  sources={srcs}")
    pres = collections.Counter(); types = collections.defaultdict(set); vals = collections.defaultdict(set)
    for _, o in items:
        for k, v in o.items():
            pres[k] += 1; types[k].add(type(v).__name__)
            if isinstance(v, (str, int, float, bool)) or v is None:
                if k in VARY or k.endswith("_id") or (isinstance(v, str) and len(v) > 40):
                    vals[k].add("<varies>")
                else:
                    vals[k].add(json.dumps(v))
    for k in sorted(pres, key=lambda k: (-pres[k], k)):
        p = "always" if pres[k] == len(items) else f"sometimes {pres[k]}/{len(items)}"
        v = sorted(vals[k])[:6]
        out.append(f"   {k:32s} {'|'.join(sorted(types[k])):14s} {p:18s} {', '.join(v)}")
(CAP / "_field-matrix.txt").write_text("\n".join(out) + "\n")
print(len(objs), "objects;", len(groups), "groups")
