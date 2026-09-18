#!/usr/bin/env python3
# Re-runnable, READ-ONLY probe of ~/.claude.json: top-level field names + types, and the per-project entry schema.
# Never prints values except (a) booleans/enums of projects this probe created under /tmp/shp-schemas-*,
# (b) counts. Usage: python3 docs/probes/2026-09-14-schemas/transcripts/probe_claude_json.py > captures/claude-json-shape.txt
import json, os, subprocess, collections
ver = subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()
d = json.load(open(os.path.expanduser('~/.claude.json')))
def t(v):
    if isinstance(v, bool): return 'bool'
    if isinstance(v, (int, float)): return 'number'
    if isinstance(v, str): return 'string'
    if isinstance(v, list): return 'array(%d)' % len(v)
    if isinstance(v, dict): return 'object(%d keys)' % len(v)
    return 'null'
print('claude_version:', ver)
print('## top-level keys (name: type)')
for k in sorted(d): print(' ', k + ':', t(d[k]))
projects = d.get('projects', {})
print('\n## projects: object keyed by absolute cwd path; %d entries' % len(projects))
pres, types = collections.Counter(), collections.defaultdict(set)
for p, e in projects.items():
    for k, v in e.items(): pres[k] += 1; types[k].add(t(v).split('(')[0])
print('## per-project fields (name: types, present in N of %d entries)' % len(projects))
for k in sorted(pres): print('  %s: %s  %d' % (k, '|'.join(sorted(types[k])), pres[k]))
vals = collections.Counter((e.get('hasTrustDialogAccepted'),) for e in projects.values())
print('\n## hasTrustDialogAccepted value counts:', dict(vals))
print('\n## entries for throwaway probe dirs (/tmp/shp-schemas-*), scalar values shown (our own sessions), arrays/objects typed only')
for p, e in projects.items():
    if p.startswith('/tmp/shp-schemas-'):
        print(' ', json.dumps(p), json.dumps({k: (v if isinstance(v, (bool, int, float, str)) or v is None else t(v)) for k, v in e.items()}))
