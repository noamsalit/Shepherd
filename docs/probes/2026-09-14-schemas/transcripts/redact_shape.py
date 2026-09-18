#!/usr/bin/env python3
# Prints the SHAPE of JSON read from stdin (or a file): keys and value types, strings replaced by <redacted>.
# Keeps literal values only for keys listed via --keep (enum-like fields) and for entries matching --session.
import json, sys, argparse
ap = argparse.ArgumentParser(); ap.add_argument('file', nargs='?'); ap.add_argument('--keep', default='')
ap.add_argument('--depth', type=int, default=6); ap.add_argument('--mask-keys', action='store_true', help='replace dict keys (e.g. paths) with <key>')
a = ap.parse_args(); keep = set(filter(None, a.keep.split(',')))
d = json.load(open(a.file) if a.file else sys.stdin)
def shape(v, k=None, depth=0):
    if isinstance(v, dict):
        if depth >= a.depth: return '<object>'
        return {('<key>' if a.mask_keys and depth == 1 else kk): shape(vv, kk, depth + 1) for kk, vv in v.items()}
    if isinstance(v, list):
        return [shape(x, k, depth + 1) for x in v[:2]] + (['...(%d items)' % len(v)] if len(v) > 2 else [])
    if isinstance(v, str): return v if k in keep else '<redacted str>'
    if isinstance(v, bool): return v if k in keep else '<bool>'
    if isinstance(v, (int, float)): return v if k in keep else '<%s>' % type(v).__name__
    return None
print(json.dumps(shape(d), indent=1, ensure_ascii=False))
