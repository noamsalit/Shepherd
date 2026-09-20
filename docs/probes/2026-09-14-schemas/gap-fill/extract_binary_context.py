#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): print the bytes around selected identifiers in the installed Claude Code binary
(no `strings` on this host). Used where a value could not be provoked live, to record what code emits it.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/extract_binary_context.py
Output:  docs/probes/2026-09-14-schemas/gap-fill/binary-context-<stamp>/context.txt"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import Run
R = Run("binary-context")
path = os.path.realpath("/root/.local/bin/claude")
data = open(path, "rb").read()
out = [f"binary: {path} ({len(data)} bytes)\n"]
for pat in [b"agent_needs_input", b"elicitation_url_dialog", b"worker_permission_prompt", b"Client does not support URL-mode",
            b"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", b"CLAUDE_CODE_AUTO_COMPACT_WINDOW", b"Unknown --effort value", b'"logout"', b"prompt_input_exit"]:
    ms = list(re.finditer(re.escape(pat), data))
    out.append(f"\n=== {pat.decode()} : {len(ms)} occurrences\n")
    seen = set()
    for m in ms[:8]:
        s = re.sub(r"[^\x20-\x7e]", ".", data[max(0, m.start() - 300):m.end() + 300].decode("latin1"))
        if s in seen:
            continue
        seen.add(s); out.append("  " + s + "\n  ---\n")
R.save("context.txt", "".join(out))
print(R.path("context.txt"))
