import json,sys,collections,hashlib
tot=0; allc=collections.Counter()
for f in sys.argv[1:]:
    c=collections.Counter(); sids=set(); keys=collections.defaultdict(set); cwds=set()
    raw=open(f,'rb').read()
    for l in raw.decode().splitlines():
        if not l.strip(): continue
        d=json.loads(l); p=d.get('payload',{})
        e=p.get('hook_event_name'); c[e]+=1; sids.add(p.get('session_id')); cwds.add(p.get('cwd'))
        keys[e]|=set(p.keys())
    n=sum(c.values()); tot+=n; allc+=c
    print(f, 'sha256', hashlib.sha256(raw).hexdigest()[:16], 'events', n, 'sessions', len(sids), 'cwds', cwds)
    print('   ', dict(c))
print('TOTAL', tot, dict(allc), 'types', len(allc))
