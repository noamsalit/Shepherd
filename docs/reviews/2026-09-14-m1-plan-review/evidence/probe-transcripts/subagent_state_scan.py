# Read-only: for each subagent meta.json, where does its toolUseId / agentId appear (session transcript vs parent-agent transcript)?
import json,glob,os
os.chdir(os.path.expanduser('~/.claude/projects'))
def scan(path, needle):
    hits=[]
    if not os.path.exists(path): return 'MISSING'
    with open(path) as fh:
        for i,line in enumerate(fh):
            if needle in line:
                o=json.loads(line); kind=o.get('type'); extra=''
                if kind=='user':
                    c=o['message'].get('content')
                    extra=[(it.get('type'), it.get('tool_use_id')==needle) for it in c if isinstance(it,dict)] if isinstance(c,list) else 'str:'+str(c)[:60]
                if kind=='queue-operation': extra=(o.get('operation'), str(o.get('content'))[:90])
                hits.append((i,kind,extra))
    return hits[:5]
for meta in sorted(glob.glob('*/*/subagents/**/*.meta.json',recursive=True)):
    if 'shp-' in meta and 'transcript-probe' not in meta: continue  # skip other reviewers' live probes
    m=json.load(open(meta)); m.pop('description',None)
    sesdir=meta.split('/subagents/')[0]; parent=sesdir+'.jsonl'
    print('==', meta.split('/',1)[1], m)
    tu=m.get('toolUseId')
    print('  PD-09 tool_result for toolUseId in SESSION transcript:', scan(parent,tu) if tu else 'NO toolUseId in meta')
    if m.get('parentAgentId'):
        print('  ... in PARENT AGENT transcript:', scan(sesdir+'/subagents/agent-'+m['parentAgentId']+'.jsonl', tu))
