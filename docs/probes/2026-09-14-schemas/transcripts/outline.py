#!/usr/bin/env python3
# Prints one line per transcript entry: index, type, subtype/attachment type, sessionId prefix, uuid prefix, extra keys.
import json, sys
COMMON = {'parentUuid','isSidechain','type','uuid','timestamp','userType','entrypoint','cwd','sessionId','version','gitBranch','message','attachment','rendered'}
for path in sys.argv[1:]:
    print('==', path)
    for i, l in enumerate(open(path)):
        try: d = json.loads(l)
        except Exception as e: print(i, 'MALFORMED', e); continue
        sub = d.get('subtype') or (d.get('attachment') or {}).get('type', '')
        m = d.get('message') if isinstance(d.get('message'), dict) else {}
        c = m.get('content')
        ct = ','.join(x.get('type','?') for x in c) if isinstance(c, list) else ('str' if isinstance(c, str) else '')
        print(i, d.get('type'), sub, (d.get('sessionId') or '')[:8], (d.get('uuid') or '')[:8], m.get('model',''), ct, sorted(set(d) - COMMON))
