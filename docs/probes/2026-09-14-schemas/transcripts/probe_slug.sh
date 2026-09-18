#!/usr/bin/env bash
# Re-runnable probe: which ~/.claude/projects/<slug>/ directory does a cwd map to?
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_slug.sh
# Runs one 1-turn haiku session per test cwd (mktemp -d under /tmp), finds the transcript by session id,
# and compares the real directory name with the naive rule "every non [A-Za-z0-9] char -> '-'".
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
V="$(claude --version)"; OUT="$C/slug-results.jsonl"; : > "$OUT"
BASE="$(mktemp -d /tmp/shp-schemas-slug.XXXXXX)"
LONG="$BASE/$(printf 'x%.0s' $(seq 1 120))/$(printf 'y%.0s' $(seq 1 110))/leaf"
for rel in "dots.and_under_scores" "with space" "ünïcødé-日本" "a--b..c" "UPPER.Case-9" ; do
  mkdir -p "$BASE/$rel"
done
mkdir -p "$LONG"
# boundary cases: cwd of exactly 200 and 201 characters, and an astral-plane (emoji) character
L200="$BASE/$(printf 'z%.0s' $(seq 1 $((200 - ${#BASE} - 1))))"
L201="$BASE/$(printf 'w%.0s' $(seq 1 $((201 - ${#BASE} - 1))))"
EMO="$BASE/emoji-😀-x"
mkdir -p "$L200" "$L201" "$EMO"
for d in "$BASE/dots.and_under_scores" "$BASE/with space" "$BASE/ünïcødé-日本" "$BASE/a--b..c" "$BASE/UPPER.Case-9" "$LONG" "$L200" "$L201" "$EMO"; do
  mkdir -p "$d/.claude"; echo '{"enabledPlugins":{"cc10x@cc10x":false}}' > "$d/.claude/settings.json"
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())')
  (cd "$d" && timeout 120 claude -p "Reply with exactly OK." --model claude-haiku-4-5-20251001 --session-id "$ID" --max-turns 1 < /dev/null > /dev/null 2>&1)
  F=$(ls /root/.claude/projects/*/"$ID".jsonl 2>/dev/null | head -1)
  python3 - "$d" "$F" "$ID" "$V" >> "$OUT" <<'PY'
import sys, json, re, os
cwd, f, sid, ver = sys.argv[1:5]
real = os.path.basename(os.path.dirname(f)) if f else None
naive = re.sub(r'[^A-Za-z0-9]', '-', cwd)
first_cwd = None
if f:
    for l in open(f):
        d = json.loads(l)
        if 'cwd' in d: first_cwd = d['cwd']; break
def jhash_b36(s):
    b = s.encode('utf-16-le'); h = 0
    for i in range(0, len(b), 2):
        h = (31 * h + int.from_bytes(b[i:i+2], 'little')) & 0xffffffff
    if h >= 2**31: h -= 2**32
    n, o = abs(h), ''
    while n: o = '0123456789abcdefghijklmnopqrstuvwxyz'[n % 36] + o; n //= 36
    return o or '0'
naive16 = re.sub(r'[^A-Za-z0-9]', '-', ''.join(chr(int.from_bytes(cwd.encode('utf-16-le')[i:i+2], 'little')) if 0xD800 <= int.from_bytes(cwd.encode('utf-16-le')[i:i+2], 'little') <= 0xDFFF else cwd.encode('utf-16-le')[i:i+2].decode('utf-16-le') for i in range(0, len(cwd.encode('utf-16-le')), 2)))
derived = naive16 if len(naive16) <= 200 else naive16[:200] + '-' + jhash_b36(cwd)
print(json.dumps({"derived_rule": derived, "derived_equals_real": derived == real, "claude_version": ver, "session_id": sid, "cwd": cwd, "cwd_chars": len(cwd), "cwd_utf8_bytes": len(cwd.encode()),
                  "real_dir": real, "real_len": len(real) if real else None, "naive_rule": naive, "naive_len": len(naive),
                  "naive_equals_real": naive == real, "transcript_cwd_field": first_cwd}, ensure_ascii=False))
PY
done
echo "base: $BASE" >> "$C/slug-meta.txt"
