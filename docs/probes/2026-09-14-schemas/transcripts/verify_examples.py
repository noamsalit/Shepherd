#!/usr/bin/env python3
# Checks that every fragment (split on "...") of every line inside fenced example blocks of SECTION.md
# occurs verbatim in some file under captures/ or copies/. Rule blocks (no quotes/braces) are reported, not failed.
import re, pathlib, sys
root = pathlib.Path(__file__).parent
corpus = [p.read_text(errors='replace') for p in list((root/'captures').rglob('*')) + list((root/'copies').rglob('*')) if p.is_file()]
text = (root/'SECTION.md').read_text()
bad = 0
for m in re.finditer(r'```(json|text)\n(.*?)```', text, re.S):
    for line in m.group(2).splitlines():
        for frag in line.split('...'):
            frag = frag.strip()
            if len(frag) < 12: continue
            if not any(frag in c for c in corpus):
                bad += 1; print('NOT FOUND:', frag[:150])
print('unmatched fragments:', bad)
