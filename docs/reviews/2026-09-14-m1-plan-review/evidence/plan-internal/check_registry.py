"""Mechanical cross-check of the M1 plan: Consumes/Produces vs Spec S4 registry and task dependencies."""
import re, sys, collections
P = "/root/Shepherd/docs/plans/2026-09-13-m1-foundation-visibility-plan.md"
text = open(P).read()
lines = text.splitlines()

# --- tasks
tasks = {}
cur = None
for i, l in enumerate(lines, 1):
    m = re.match(r"^### Task (T\d+b?):", l)
    if m:
        cur = m.group(1); tasks[cur] = {"line": i, "consumes": [], "produces": [], "deps": []}
        continue
    if cur is None: continue
    if l.startswith("## ") : cur = None; continue
    m = re.match(r"^- \*\*(Consumes|Produces|Dependencies):\*\*\s*(.*)$", l)
    if m:
        key, val = m.group(1), m.group(2)
        if key == "Dependencies":
            tasks[cur]["deps"] = re.findall(r"T\d+b?", val)
        else:
            names = re.findall(r"`([^`]+)`", val)
            tasks[cur][key.lower()] = names

def closure(t, seen=None):
    seen = seen if seen is not None else set()
    for d in tasks[t]["deps"]:
        if d not in seen:
            seen.add(d); closure(d, seen)
    return seen

producer = collections.defaultdict(list)
for t, d in tasks.items():
    for n in d["produces"]:
        producer[n].append(t)

print("== Names produced by more than one task")
for n, ts in producer.items():
    if len(ts) > 1: print(f"  {n}: {ts}")

print("== Consumed names not produced by any task")
for t, d in tasks.items():
    for n in d["consumes"]:
        if n not in producer: print(f"  {t} consumes {n!r}: no producer")

print("== Consumed names whose producer is NOT in the consumer's transitive Dependencies")
for t, d in tasks.items():
    cl = closure(t)
    for n in d["consumes"]:
        ps = producer.get(n, [])
        if ps and not any(p in cl or p == t for p in ps):
            print(f"  {t} (deps closure {sorted(cl)}) consumes {n!r} produced by {ps}")

# --- registry
s = text.index("## Spec S4")
e = text.index("## Phase Plan")
reg = text[s:e]
sections = re.split(r"# ---- (T\d+) -+", reg)
regnames = {}
for k in range(1, len(sections), 2):
    t = sections[k]; body = sections[k+1]
    names = set()
    for bl in body.splitlines():
        bl2 = bl.split("#",1)[0] if not bl.strip().startswith("# shepherd") else ""
        for m in re.finditer(r"^\s*(?:@dataclass\(frozen=True\)\s*)?(?:class|def|type)\s+([A-Za-z_][A-Za-z0-9_]*)", bl2):
            names.add(m.group(1))
        for m in re.finditer(r"(?:^|;\s*)([A-Z][A-Z0-9_]+)\s*:\s*Final", bl2):
            names.add(m.group(1))
        m = re.match(r"^([A-Z][A-Z0-9_]+)\s*:\s*Final", bl2.strip())
        if m: names.add(m.group(1))
        m = re.match(r"^\s{4}def\s+([a-z_]+)", bl)  # methods: skip
    regnames[t] = names

print("== Registry top-level names missing from the same task's Produces")
for t, names in regnames.items():
    prod = set(tasks.get(t, {}).get("produces", []))
    miss = sorted(n for n in names if n not in prod and n not in {"main"} )
    if miss: print(f"  {t}: {miss}")
print("== Produces names (identifiers) not present anywhere in registry section of that task")
for t, d in tasks.items():
    if t not in regnames: 
        print(f"  {t}: no registry section"); continue
    for n in d["produces"]:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) and n not in regnames[t]:
            print(f"  {t} produces {n!r} not declared in its S4 section")
