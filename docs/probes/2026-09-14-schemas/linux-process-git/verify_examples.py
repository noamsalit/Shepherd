#!/usr/bin/env python3
"""Check that every fenced example in SECTION.md is copied from its cited capture file.

Re-run: python3 docs/probes/2026-09-14-schemas/linux-process-git/verify_examples.py

For each fenced block, the capture is the last `captures/...` path mentioned between the previous block and this
one. The block is split on "..." (the trimming marker); every non-empty fragment, with surrounding whitespace
stripped, must occur verbatim in that capture file. Exit 1 on any miss.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
text = open(os.path.join(HERE, "SECTION.md")).read()
parts = re.split(r"^```[a-z]*\n(.*?)^```\n", text, flags=re.S | re.M)
bad = 0
checked = 0
for i in range(1, len(parts), 2):
    prose, block = parts[i - 1], parts[i]
    caps = re.findall(r"`(captures/[^`]+)`", prose)
    if not caps:
        print(f"block {i//2+1}: no capture cited"); bad += 1; continue
    cap = caps[-1]
    body = open(os.path.join(HERE, cap), encoding="utf-8", errors="replace").read()
    for frag in block.split("..."):
        f = frag.strip()
        if not f:
            continue
        checked += 1
        if f not in body:
            # allow line-wise match when a fragment spans lines that are individually present in order
            print(f"MISS block {i//2+1} ({cap}): {f[:160]!r}")
            bad += 1
print(f"fragments checked: {checked}, misses: {bad}")
sys.exit(1 if bad else 0)
