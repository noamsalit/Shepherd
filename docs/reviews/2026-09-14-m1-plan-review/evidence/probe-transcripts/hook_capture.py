#!/usr/bin/env python3
# Probe hook: append raw stdin + event name + timestamp + ps ancestry to a JSONL file. Always exits 0.
import sys, json, os, datetime, subprocess
out = os.environ.get('PROBE_OUT') or sys.argv[2]
ev = sys.argv[1]
raw = sys.stdin.read()
chain = []
pid = os.getpid()
try:
    for _ in range(12):
        r = subprocess.run(['ps', '-o', 'pid=,ppid=,comm=,args=', '-p', str(pid)], capture_output=True, text=True, timeout=2).stdout.strip()
        if not r: break
        parts = r.split(None, 3)
        chain.append({'pid': parts[0], 'ppid': parts[1], 'comm': parts[2], 'args': (parts[3] if len(parts) > 3 else '')[:200]})
        if parts[1] in ('0', '1'): break
        pid = int(parts[1])
except Exception as e:
    chain.append({'error': str(e)})
rec = {'hook_event_name_arg': ev, 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'ancestry': chain, 'raw_stdin': raw}
with open(out, 'a') as fh:
    fh.write(json.dumps(rec) + '\n')
sys.exit(0)
