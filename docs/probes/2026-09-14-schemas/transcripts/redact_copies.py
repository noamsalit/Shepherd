#!/usr/bin/env python3
# Privacy pass over copied captures: account email and account/org UUIDs that Claude Code injects
# into every session are replaced in place. Everything else stays byte-for-byte.
import re, sys, pathlib
root = pathlib.Path(sys.argv[1])
pats = [(re.compile(r'[A-Za-z0-9._%+-]+@(gmail|googlemail)\.com'), '<redacted-email>'),
        (re.compile(r'("(?:owner)?(?:Account|Organization|account|organization)Uuid"\s*:\s*")[0-9a-f-]{36}(")'), r'\1<redacted-uuid>\2')]
n = 0
for p in root.rglob('*'):
    if p.is_file() and p.suffix in ('.jsonl', '.json', '.txt', '.md'):
        s = p.read_text(errors='surrogateescape'); t = s
        for rx, rep in pats: t = rx.sub(rep, t)
        if t != s: p.write_text(t, errors='surrogateescape'); n += 1
print('files redacted:', n)
