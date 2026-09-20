#!/usr/bin/env python3
# READ-ONLY: key presence and enum values across ~/.claude/sessions/<pid>.json (never reads *.key files, never prints free text).
# Usage: python3 docs/probes/2026-09-14-schemas/transcripts/stats_registry.py > captures/registry-stats.json
import json, glob, os, subprocess, collections as co
keys, enums, n = co.Counter(), co.defaultdict(co.Counter), 0
files = sorted(glob.glob(os.path.expanduser('~/.claude/sessions/*.json')))
for f in files:
    try: d = json.load(open(f))
    except Exception: keys['<unparseable>'] += 1; continue
    n += 1
    for k, v in d.items():
        keys[k] += 1
        if k in ('kind', 'entrypoint', 'status', 'nameSource', 'peerProtocol', 'version'): enums[k][str(v)] += 1
        elif k == 'peerFeatures': [enums[k].__setitem__(x, enums[k][x] + 1) for x in v]
        elif k == 'bridgeSessionId': enums['bridgeSessionId.prefix'][str(v).split('_')[0]] += 1
print(json.dumps({'claude_version': subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip(),
                  'registry_json_files': n, 'key_files_present(not read)': len(glob.glob(os.path.expanduser('~/.claude/sessions/*.key'))),
                  'key_presence': dict(keys), 'enum_values': {k: dict(v) for k, v in enums.items()}}, indent=1))
