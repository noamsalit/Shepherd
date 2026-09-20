#!/usr/bin/env bash
# Re-runnable probe: live-session registry (~/.claude/sessions/<pid>.json) and `claude agents --json`,
# observed while one throwaway `claude -p` session (haiku) is sleeping inside a Bash tool call.
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_registry.sh
# Only the throwaway session's entries are stored raw; everyone else's entries are stored as redacted shapes.
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
V="$(claude --version)"; echo "claude_version: $V" > "$C/registry-meta.txt"; date -u +%FT%TZ >> "$C/registry-meta.txt"
W="$(mktemp -d /tmp/shp-schemas-reg.XXXXXX)/work"; mkdir -p "$W/.claude"
echo '{"enabledPlugins":{"cc10x@cc10x":false}}' > "$W/.claude/settings.json"
ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/registry-session-id.txt"
(cd "$W" && timeout 150 claude -p "Run the Bash command: sleep 40. Then reply with exactly OK." --model claude-haiku-4-5-20251001 \
   --session-id "$ID" --name "shp registry probe" --max-turns 3 --allowedTools "Bash(sleep *)" < /dev/null > "$C/registry-stdout.txt" 2>&1) &
RUNNER=$!
sleep 15
MY=$(grep -l "\"sessionId\":\"$ID\"" /root/.claude/sessions/*.json 2>/dev/null | head -1)
echo "registry_file: $MY" >> "$C/registry-meta.txt"
[ -n "$MY" ] && { python3 -m json.tool "$MY" > "$C/registry-own-session.json"; ls -la "$(dirname "$MY")" | sed -E 's/[0-9a-f]{64}/<hash>/' > "$C/registry-dir-listing.txt"; }
timeout 30 claude agents --json > "$C/agents-json-raw.tmp" 2> "$C/agents-json-stderr.txt"; echo "agents_json_exit: $?" >> "$C/registry-meta.txt"
timeout 30 claude agents --json --all > "$C/agents-json-all-raw.tmp" 2>> "$C/agents-json-stderr.txt"; echo "agents_json_all_exit: $?" >> "$C/registry-meta.txt"
for f in agents-json agents-json-all; do
python3 - "$C/$f-raw.tmp" "$ID" "$C/$f-own.json" "$C/$f-others-shape.json" <<'PY'
import json, sys, subprocess
raw, sid, own_out, others_out = sys.argv[1:5]
try: d = json.load(open(raw))
except Exception as e:
    open(own_out, 'w').write(json.dumps({"parse_error": str(e), "bytes": len(open(raw).read())})); sys.exit()
own = [x for x in d if sid in json.dumps(x)]
others = [x for x in d if sid not in json.dumps(x)]
json.dump({"total_entries": len(d), "own": own}, open(own_out, 'w'), indent=1)
def shape(v, k=None):
    if isinstance(v, dict): return {kk: shape(vv, kk) for kk, vv in v.items()}
    if isinstance(v, list): return [shape(x, k) for x in v[:2]]
    if isinstance(v, str): return v if k in ('kind', 'status', 'state', 'entrypoint', 'nameSource', 'source', 'type') else '<redacted str>'
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return '<%s>' % type(v).__name__
    return v
json.dump({"count": len(others), "shapes": [shape(x) for x in others]}, open(others_out, 'w'), indent=1)
PY
rm -f "$C/$f-raw.tmp"
done
wait $RUNNER
echo "after_exit_registry_file_exists: $( [ -n "$MY" ] && [ -f "$MY" ] && echo yes || echo no)" >> "$C/registry-meta.txt"
# redact account email if Claude Code injected it anywhere we stored
sed -i -E 's/[A-Za-z0-9._%+-]+@(gmail|googlemail)\.com/<redacted-email>/g' "$C"/registry-* "$C"/agents-json-* 2>/dev/null
