"""For each task body, find backticked registry names (anywhere in the task text) whose producing task
is neither the task itself nor in its transitive Dependencies. These are references the Consumes line does not declare."""
import re, collections
exec(open("/root/Shepherd/docs/reviews/2026-09-14-m1-plan-review/evidence/plan-internal/check_registry.py").read().split("# --- registry")[0].replace('print(', '(lambda *a, **k: None)('))
bodies = {}
order = sorted(tasks, key=lambda t: tasks[t]["line"])
for idx, t in enumerate(order):
    start = tasks[t]["line"]
    end = tasks[order[idx+1]]["line"] - 1 if idx + 1 < len(order) else len(lines)
    bodies[t] = "\n".join(lines[start-1:end])
for t in order:
    cl = closure(t) | {t}
    toks = set()
    for m in re.finditer(r"`([^`]+)`", bodies[t]):
        for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", m.group(1)):
            toks.add(w)
    declared = set(tasks[t]["consumes"])
    for w in sorted(toks):
        ps = producer.get(w)
        if not ps or w == "main": continue
        if not any(p in cl for p in ps):
            print(f"{t}: references `{w}` produced by {ps}, not in deps closure {sorted(cl - {t})}")
        elif w not in declared and t not in ps:
            print(f"{t}: uses `{w}` (from {ps}) but it is not in its Consumes line")
