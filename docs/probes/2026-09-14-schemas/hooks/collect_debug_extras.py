#!/usr/bin/env python3
"""Copy non-hook debug lines that SECTION.md cites (wind-down, auto-mode, engine turn, API errors,
trust, SessionEnd) from each run's /tmp debug log into live/<run>/debug-extras.txt (2026-09-14).
Re-run right after run_probes.py (the /tmp dirs must still exist):
  python3 docs/probes/2026-09-14-schemas/hooks/collect_debug_extras.py
"""
import glob, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
PAT = re.compile(r"wind-down|auto mode|\[auto-mode\]|\[engine\]|API error|trust|SessionEnd|StopFailure|Shutting down|shut down")
for mp in sorted(glob.glob(os.path.join(HERE, "live", "*", "meta.json"))):
    m = json.load(open(mp)); d = m.get("cwd")
    logs = glob.glob(os.path.join(d, ".debug-*.log")) if d else []
    if not logs:
        continue
    name = os.path.basename(os.path.dirname(mp))
    mine = [l for l in logs if name in l or name.startswith("I01")] or logs
    out = [f"# claude {m.get('claude_version')}; source {mine[0]}\n"]
    for line in open(mine[0], errors="replace"):
        if PAT.search(line):
            out.append(line)
    open(os.path.join(os.path.dirname(mp), "debug-extras.txt"), "w").writelines(out)
    print(name, len(out) - 1)
