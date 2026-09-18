#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): resume a session across Claude Code versions (spec 1535, 1552-1553:
# "one continuous orchestrator conversation across restarts, reboots, and upgrades").
#   A) create with the Agent-SDK-bundled CLI (2.1.259), resume with the system CLI (2.1.270)
#   B) create with 2.1.270, resume with 2.1.259
# Real API, haiku, one short turn each, throwaway cwd, --settings disables cc10x, CLAUDE* env scrubbed.
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_cross_version_resume.sh [<path to 2.1.259 binary>]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/cross-version-resume-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
OLD="${1:-/tmp/shp-sdk-9IOKNs/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude}"
NEW="$(readlink -f /root/.local/bin/claude)"
{ echo "claude --version: $(claude --version)"; echo "old binary: $OLD -> $($OLD --version)"; echo "new binary: $NEW -> $($NEW --version)"; uname -sr; } > "$OUT/versions.txt"
W="$(mktemp -d /tmp/shp-gap-xver-XXXXXX)"; echo "$W" > "$OUT/tmpdir.txt"
echo '{"enabledPlugins":{"cc10x@cc10x":false},"remoteControlAtStartup":false}' > "$W/flag-settings.json"
C(){ local bin="$1"; shift; ( cd "$W" && env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_SSE_PORT DISABLE_AUTOUPDATER=1 timeout 120 "$bin" -p --model claude-haiku-4-5-20251001 --settings "$W/flag-settings.json" --output-format json "$@" < /dev/null ); }
summ(){ python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d.get(k) for k in ("type","subtype","is_error","result","session_id","num_turns")}))'; }
versions(){ python3 - "$1" <<'PY'
import json, sys, collections
c = collections.Counter()
for l in open(sys.argv[1]):
    try: d = json.loads(l)
    except Exception: c["UNPARSEABLE"] += 1; continue
    c[(d.get("type"), d.get("version"))] += 1
print(json.dumps({f"{t}|{v}": n for (t, v), n in sorted(c.items(), key=str)}))
PY
}
for case in A B; do
  if [ $case = A ]; then MK="$OLD"; RS="$NEW"; WORD="KIWI-259"; else MK="$NEW"; RS="$OLD"; WORD="MELON-270"; fi
  R1="$(C "$MK" -- "Remember this code word: $WORD. Reply with only OK." 2>"$OUT/$case-create.stderr")"
  echo "$R1" | summ > "$OUT/$case-create.json" 2>>"$OUT/$case-create.stderr"
  SID="$(echo "$R1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')"
  T="$(ls /root/.claude/projects/*/"$SID".jsonl 2>/dev/null | head -1)"
  echo "transcript=$T" > "$OUT/$case-ids.txt"; echo "session_id=$SID" >> "$OUT/$case-ids.txt"
  echo "size_before_resume=$(stat -c %s "$T") sha256_before=$(sha256sum "$T" | cut -d' ' -f1)" >> "$OUT/$case-ids.txt"
  versions "$T" > "$OUT/$case-versions-after-create.json"
  R2="$(C "$RS" --resume "$SID" -- "What was the code word? Reply with only the code word." 2>"$OUT/$case-resume.stderr")"; echo "resume exit=$?" >> "$OUT/$case-ids.txt"
  echo "$R2" | summ > "$OUT/$case-resume.json" 2>>"$OUT/$case-resume.stderr"
  PREV=$(grep -o 'size_before_resume=[0-9]*' "$OUT/$case-ids.txt" | cut -d= -f2)
  echo "size_after_resume=$(stat -c %s "$T") prefix_unchanged=$(head -c "$PREV" "$T" | sha256sum | cut -d' ' -f1)" >> "$OUT/$case-ids.txt"
  versions "$T" > "$OUT/$case-versions-after-resume.json"
done
for f in "$OUT"/*.json "$OUT"/*-ids.txt "$OUT"/*.stderr; do echo "== $(basename "$f")"; cat "$f"; done
