#!/usr/bin/env python3
# Probe hook: append raw stdin JSON + event name + our timestamp + claude version + parent process chain
# to a JSONL file. Always exits 0 so it can never block Claude Code.
import sys, json, os, datetime, subprocess
ev, out = sys.argv[1], sys.argv[2]
raw = sys.stdin.read()
chain, pid = [], os.getpid()
try:
    for _ in range(12):
        r = subprocess.run(['ps', '-o', 'pid=,ppid=,comm=,args=', '-p', str(pid)],
                           capture_output=True, text=True, timeout=2).stdout.strip()
        if not r:
            break
        p = r.split(None, 3)
        chain.append({'pid': p[0], 'ppid': p[1], 'comm': p[2], 'args': (p[3] if len(p) > 3 else '')[:160]})
        if p[1] in ('0', '1'):
            break
        pid = int(p[1])
except Exception as e:
    chain.append({'error': str(e)})
rec = {'event_arg': ev, 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'claude_version': os.environ.get('PROBE_CLAUDE_VERSION', ''), 'ancestry': chain, 'raw_stdin': raw}
try:
    with open(out, 'a') as fh:
        fh.write(json.dumps(rec) + '\n')
except Exception:
    pass
sys.exit(0)
