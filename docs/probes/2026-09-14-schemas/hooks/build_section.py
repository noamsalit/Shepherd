#!/usr/bin/env python3
"""Render SECTION.md from SECTION.tmpl.md, pulling every example byte-for-byte from the
raw capture files (2026-09-14). Re-run after re-running probes:

  python3 docs/probes/2026-09-14-schemas/hooks/build_section.py

Markers (one per line in the template):
  <<EX live/<run>/events.jsonl|Event|nth|k=v,k=v|maxlen>>   raw hook payload (excerpt.py; long strings trimmed with ...)
  <<RAW relpath|python-regex|maxlen>>                        first regex match (re.M) in the file, trimmed with ...
  <<ENV relpath|nth>>                                        the "_env" object of the nth env.jsonl record, <not-recorded> entries elided as ...
  <<LINES relpath|a|b>>                                      lines a..b (1-based, inclusive) of a text file
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from excerpt import excerpt, trim  # noqa: E402

tmpl = open(os.path.join(HERE, "SECTION.tmpl.md"), encoding="utf8").read()


def p(rel):
    return os.path.join(HERE, rel)


def ex(m):
    path, ev, nth, filt, mx = (m.group(1).split("|") + ["", "", ""])[:5]
    filters = dict(kv.split("=", 1) for kv in filt.split(",") if kv) if filt else {}
    text, _ = excerpt(p(path), ev, int(nth or 1), filters, int(mx or 140))
    return text


def raw(m):
    path, rest = m.group(1).split("|", 1)
    rx, mx = rest.rsplit("|", 1)  # maxlen is mandatory, so the regex may contain '|'
    data = open(p(path), encoding="utf8", errors="replace").read()
    mm = re.search(rx, data, re.M)
    if not mm:
        raise SystemExit(f"RAW no match: {path} {rx}")
    return trim(mm.group(0), int(mx or 140))


def env(m):
    path, nth = m.group(1).split("|")
    line = open(p(path), encoding="utf8").read().splitlines()[int(nth) - 1]
    obj = re.search(r'"_env": \{[^}]*\}', line).group(0)
    t = re.sub(r'(, )?"[^"]+": "<not-recorded>"', ", ...", obj).replace("{, ...", "{...")
    return re.sub(r"(, \.\.\.)(, \.\.\.)+", ", ...", t)


def lines(m):
    path, a, b = m.group(1).split("|")
    ls = open(p(path), encoding="utf8").read().splitlines()
    return "\n".join(ls[int(a) - 1:int(b)])


def common_matrix(_m):
    import glob, collections
    fields = ["session_id", "transcript_path", "cwd", "hook_event_name", "prompt_id", "permission_mode",
              "effort", "agent_id", "agent_type", "scratchpad_dir"]
    n = collections.Counter(); c = collections.defaultdict(collections.Counter)
    for f in glob.glob(p("live/*/events.jsonl")):
        for line in open(f, encoding="utf8"):
            r = json.loads(line); pl = r["payload"]; ev = pl.get("hook_event_name")
            n[ev] += 1
            for k in fields:
                if k in pl:
                    c[ev][k] += 1
    hdr = "| Event (n captures) | " + " | ".join(f"`{k}`" for k in fields) + " |\n"
    hdr += "|---" * (len(fields) + 1) + "|\n"
    rows = []
    for ev in sorted(n):
        cells = []
        for k in fields:
            v = c[ev][k]
            cells.append("always" if v == n[ev] else ("never" if v == 0 else f"{v}/{n[ev]}"))
        rows.append(f"| {ev} ({n[ev]}) | " + " | ".join(cells) + " |")
    return hdr + "\n".join(rows)


out = tmpl
out = re.sub(r"<<COMMONMATRIX>>", common_matrix, out)
out = re.sub(r"<<EX (.+?)>>", ex, out)
out = re.sub(r"<<RAW (.+?)>>", raw, out)
out = re.sub(r"<<ENV (.+?)>>", env, out)
out = re.sub(r"<<LINES (.+?)>>", lines, out)
open(os.path.join(HERE, "SECTION.md"), "w", encoding="utf8").write(out)
print("wrote SECTION.md", len(out), "chars")
