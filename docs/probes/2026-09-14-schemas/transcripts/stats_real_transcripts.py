#!/usr/bin/env python3
# READ-ONLY statistics over every transcript under ~/.claude/projects. Emits counts, field names, and values ONLY for
# enum-like fields (type/subtype/model ids/effort/trigger/operation...). Never emits free text. Probe dirs
# (/tmp/shp-* throwaways) are reported separately from the user's own dirs.
# Usage: python3 docs/probes/2026-09-14-schemas/transcripts/stats_real_transcripts.py > captures/real-transcripts-stats.json
import json, os, re, subprocess, collections as co, pathlib
ROOT = pathlib.Path.home() / '.claude' / 'projects'
ENUM_RX = re.compile(r'^[A-Za-z0-9_.:<>\-\[\]]{1,60}$')
def is_probe(d): return d.name.startswith('-tmp-shp-')
def new(): return {'files': co.Counter(), 'types': co.Counter(), 'keys': co.defaultdict(co.Counter), 'enums': co.defaultdict(co.Counter),
                   'lastPrompt': co.Counter(), 'usage_keys': co.Counter(), 'meta_keys': co.Counter(), 'journal': co.defaultdict(co.Counter),
                   'sidecar_keys': co.defaultdict(co.Counter), 'malformed_lines': 0, 'title_entries_per_main_file': co.Counter()}
S = {'user_dirs': new(), 'probe_dirs': new()}
def enum(b, name, v):
    if v is None or isinstance(v, bool) or (isinstance(v, str) and ENUM_RX.match(v)): b['enums'][name][str(v)] += 1
    elif isinstance(v, (int, float)): b['enums'][name]['<number>'] += 1
    else: b['enums'][name]['<free text redacted>'] += 1
for proj in sorted(ROOT.iterdir()):
    if not proj.is_dir(): continue
    b = S['probe_dirs' if is_probe(proj) else 'user_dirs']
    for p in proj.rglob('*'):
        if not p.is_file(): continue
        rel = p.relative_to(proj).parts
        kind = ('main.jsonl' if len(rel) == 1 and p.suffix == '.jsonl' else
                'workflow agent jsonl' if 'workflows' in rel and p.name.startswith('agent-') and p.suffix == '.jsonl' else
                'workflow agent meta.json' if 'workflows' in rel and p.name.endswith('.meta.json') else
                'workflow journal.jsonl' if p.name == 'journal.jsonl' else
                'subagent jsonl' if 'subagents' in rel and p.suffix == '.jsonl' else
                'subagent meta.json' if p.name.endswith('.meta.json') else
                '/'.join(['<sid>' if re.match(r'^[0-9a-f-]{36}$', x) else re.sub(r'[0-9a-f]{8,}', '<hex>', x) for x in rel[:-1]] +
                         [re.sub(r'\.[^.]+$', '', 'x') and ('*' + p.suffix if not p.name.endswith('.meta.json') else p.name)]))
        b['files'][kind] += 1
        if p.name.endswith('.meta.json'):
            try:
                m = json.load(open(p))
                for k, v in m.items():
                    b['meta_keys'][k] += 1
                    if k in ('requestShape', 'spawnDepth', 'requestNonInteractive', 'model', 'workflowPhase' if False else 'x'): enum(b, 'meta.' + k, v)
            except Exception: b['meta_keys']['<unparseable>'] += 1
            continue
        if p.name == 'journal.jsonl':
            for l in open(p, errors='replace'):
                try: j = json.loads(l)
                except Exception: b['journal']['<malformed>']['-'] += 1; continue
                b['journal'][j.get('type')][','.join(sorted(j))] += 1
            continue
        if p.suffix == '.json' and 'workflows' not in rel:
            try: b['sidecar_keys'][kind][','.join(sorted(json.load(open(p))))] += 1
            except Exception: pass
            continue
        if p.suffix == '.json' and 'workflows' in rel:
            try: b['sidecar_keys'][kind][','.join(sorted(json.load(open(p))))] += 1
            except Exception: pass
            continue
        if p.suffix != '.jsonl': continue
        titles = co.Counter()
        for l in open(p, errors='replace'):
            try: d = json.loads(l)
            except Exception: b['malformed_lines'] += 1; continue
            t = d.get('type'); sub = d.get('subtype')
            if t == 'attachment' and isinstance(d.get('attachment'), dict): sub = 'attachment:' + str(d['attachment'].get('type'))
            label = t + ('/' + sub if sub and not str(sub).startswith('attachment:') else '') if t != 'attachment' else sub
            b['types'][str(label)] += 1
            for k in d: b['keys'][str(label)][k] += 1
            b['keys'][str(label)]['__total__'] += 1
            if t in ('ai-title', 'custom-title', 'agent-name'): titles[t] += 1
            if 'isSidechain' in d: enum(b, 'isSidechain[%s]' % kind, d['isSidechain'])
            if t == 'assistant':
                m = d.get('message') or {}
                enum(b, 'assistant.message.model', m.get('model'))
                enum(b, 'assistant.effort(top-level, present only)', d.get('effort', '<absent>'))
                enum(b, 'assistant.perTurnEffort', d.get('perTurnEffort', '<absent>'))
                enum(b, 'assistant.message.stop_reason', m.get('stop_reason'))
                if m.get('model') == '<synthetic>':
                    enum(b, 'synthetic.error', d.get('error')); enum(b, 'synthetic.apiErrorStatus', d.get('apiErrorStatus'))
                    enum(b, 'synthetic.isApiErrorMessage', d.get('isApiErrorMessage'))
                for k in (m.get('usage') or {}): b['usage_keys'][k] += 1
            if t == 'last-prompt':
                lp = d.get('lastPrompt')
                if lp is None: b['lastPrompt']['field absent'] += 1
                else:
                    b['lastPrompt']['len<=200' if len(lp) <= 200 else 'len>200'] += 1
                    b['lastPrompt']['max_len_seen'] = max(b['lastPrompt']['max_len_seen'], len(lp))
                    if lp.endswith('…'): b['lastPrompt']['ends with U+2026'] += 1
                    if '\n' in lp: b['lastPrompt']['contains newline'] += 1
            if t == 'system' and sub == 'compact_boundary':
                for k, v in (d.get('compactMetadata') or {}).items(): enum(b, 'compactMetadata.' + k, v if k == 'trigger' else '<number>' if isinstance(v, (int, float)) else type(v).__name__)
            if t == 'user':
                if d.get('isCompactSummary'): b['enums']['user.isCompactSummary']['true'] += 1
                o = d.get('origin')
                if isinstance(o, dict): enum(b, 'user.origin.kind', o.get('kind'))
                enum(b, 'user.promptSource', d.get('promptSource', '<absent>'))
            if t == 'queue-operation':
                enum(b, 'queue-operation.operation', d.get('operation'))
                c = d.get('content')
                if isinstance(c, str) and c.startswith('<task-notification>'): b['enums']['queue-operation.content']['starts <task-notification>'] += 1
            if t in ('mode', 'permission-mode'): enum(b, t + '.value', d.get('mode', d.get('permissionMode')))
            if 'entrypoint' in d: enum(b, 'entrypoint', d['entrypoint'])
            if 'userType' in d: enum(b, 'userType', d['userType'])
        if kind == 'main.jsonl':
            b['title_entries_per_main_file'][','.join('%s>0' % k for k in sorted(titles)) or 'none'] += 1
out = {'claude_version': subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()}
for name, b in S.items():
    out[name] = {k: ({kk: dict(vv) for kk, vv in v.items()} if isinstance(v, co.defaultdict) else dict(v) if isinstance(v, co.Counter) else v) for k, v in b.items()}
print(json.dumps(out, indent=1, sort_keys=True))
