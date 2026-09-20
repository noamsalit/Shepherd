#!/usr/bin/env python3
"""Gap-fill helper (2026-09-14): every fragment (split on "...") of every line inside a ```json / ```text block of
SECTION.md must occur verbatim in some capture file under a gap-fill run folder (scripts excluded).
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/verify_examples.py"""
import pathlib, re
root = pathlib.Path(__file__).parent
corpus = []
for p in root.glob("*-2026*/**/*"):
    if p.is_file() and p.suffix not in (".py", ".sh"):
        corpus.append(p.read_bytes().decode("utf-8", "replace"))
text = (root / "SECTION.md").read_text()
bad = n = 0
for m in re.finditer(r"```(json|text)\n(.*?)```", text, re.S):
    for line in m.group(2).splitlines():
        for frag in line.split("..."):
            frag = frag.strip()
            if len(frag) < 12:
                continue
            n += 1
            if not any(frag in c for c in corpus):
                bad += 1
                print("NOT FOUND:", frag[:160])
print(f"fragments checked: {n}, unmatched: {bad}")
