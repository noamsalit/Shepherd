#!/usr/bin/env bash
# Re-runnable probe: throwaway session lifecycle -> transcript + sidecar shapes.
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_lifecycle.sh [step...]
# Steps: main resume fork named bg compact synthetic effort   (default: all)
# Writes only to this evidence folder and a mktemp -d under /tmp. Haiku, timeouts everywhere.
set -u
E="$(cd "$(dirname "$0")" && pwd)"
C="$E/captures"; mkdir -p "$C" "$E/copies"
export PROBE_CLAUDE_VERSION="$(claude --version)"
M=claude-haiku-4-5-20251001
BASE_FILE="$C/lifecycle-base-dir.txt"
if [ -f "$BASE_FILE" ] && [ -d "$(cat "$BASE_FILE")" ]; then BASE="$(cat "$BASE_FILE")"; else BASE="$(mktemp -d /tmp/shp-schemas-tx.XXXXXX)"; echo "$BASE" > "$BASE_FILE"; fi
W="$BASE/work"; mkdir -p "$W/.claude"
python3 "$E/make_settings.py" "$E/hook_capture.py" "$C/hooks-lifecycle.jsonl" "$W/.claude/settings.json"
cp "$W/.claude/settings.json" "$C/lifecycle-settings.json"
PROJ=/root/.claude/projects

run() { # name, then claude args...
  local name="$1"; shift
  { echo "claude_version: $PROBE_CLAUDE_VERSION"; echo "date_utc: $(date -u +%FT%TZ)"; echo "cwd: $W"; printf 'argv:'; printf ' %q' claude "$@"; echo; } > "$C/$name-meta.txt"
  (cd "$W" && timeout 240 claude "$@" < /dev/null > "$C/$name-stdout.jsonl" 2> "$C/$name-stderr.txt"); echo "exit: $?" >> "$C/$name-meta.txt"
}
tfile() { ls $PROJ/*/"$1".jsonl 2>/dev/null | head -1; }
steps="${*:-main resume fork named bg compact synthetic effort workflow longprompt}"
MAIN_ID_FILE="$C/main-session-id.txt"
for s in $steps; do case $s in
main)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$MAIN_ID_FILE"
  run main -p "Step 1: use the Agent tool (subagent_type general-purpose, description 'probe child') with the prompt 'Reply with exactly the word PONG and nothing else.' Step 2: use the Write tool to create notes.txt containing hello. Step 3: reply with exactly DONE." \
     --model $M --session-id "$ID" --output-format stream-json --verbose --max-turns 8 --allowedTools Agent Write
  ;;
resume)
  ID=$(cat "$MAIN_ID_FILE"); F=$(tfile "$ID")
  { echo "file: $F"; echo "lines_before: $(wc -l < "$F")"; } > "$C/resume-filecheck.txt"
  run resume -p "Reply with exactly RESUMED." --resume "$ID" --model $M --output-format stream-json --verbose --max-turns 2
  { echo "lines_after: $(wc -l < "$F")"; echo "files_named_id: $(ls $PROJ/*/"$ID".jsonl | wc -l)"; ls -la "$(dirname "$F")"; } >> "$C/resume-filecheck.txt"
  ;;
fork)
  ID=$(cat "$MAIN_ID_FILE"); F=$(tfile "$ID")
  { echo "source_id: $ID"; echo "source_lines_before: $(wc -l < "$F")"; ls -la "$(dirname "$F")"; } > "$C/fork-filecheck.txt"
  run fork -p "Reply with exactly FORKED." --resume "$ID" --fork-session --model $M --output-format stream-json --verbose --max-turns 2
  NEW=$(python3 -c "import json,sys
for l in open('$C/fork-stdout.jsonl'):
  try: d=json.loads(l)
  except: continue
  if d.get('type')=='result': print(d['session_id'])")
  echo "$NEW" > "$C/fork-session-id.txt"
  { echo "fork_id: $NEW"; echo "source_lines_after: $(wc -l < "$F")"; echo "fork_file: $(tfile "$NEW")"; echo "fork_lines: $(wc -l < "$(tfile "$NEW")")"; ls -la "$(dirname "$F")"; } >> "$C/fork-filecheck.txt"
  ;;
named)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/named-session-id.txt"
  run named -p "Reply with exactly OK." --name "shp probe named" --session-id "$ID" --model $M --output-format stream-json --verbose --max-turns 1
  ls -laR "$(dirname "$(tfile "$ID")")/$ID" > "$C/named-sidecars.txt" 2>&1
  ;;
bg)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/bg-session-id.txt"
  run bg -p "Use the Agent tool with run_in_background set to true (subagent_type general-purpose, description 'probe bg child', prompt 'Reply with exactly BGPONG.'). Wait until you are notified it completed, then reply with exactly DONE." \
     --model $M --session-id "$ID" --output-format stream-json --verbose --max-turns 8 --allowedTools Agent
  ;;
compact)
  ID=$(cat "$MAIN_ID_FILE")
  run compact -p "/compact" --resume "$ID" --model $M --output-format stream-json --verbose
  ;;
synthetic)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/synthetic-session-id.txt"
  run synthetic -p "Reply OK." --model claude-nonexistent-model-shp --session-id "$ID" --output-format stream-json --verbose --max-turns 1
  ;;
effort)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/effort-session-id.txt"
  run effort -p "Reply with exactly OK." --effort low --session-id "$ID" --model $M --output-format stream-json --verbose --max-turns 1
  ;;
workflow)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/workflow-session-id.txt"
  SCRIPT="export const meta = { name: 'shp-probe-wf', description: 'schema probe', phases: [ { title: 'Ping' } ] }
phase('Ping')
const r = await agent('Reply with exactly the word PONG.', { label: 'ping' })
return r"
  run workflow -p "Call the Workflow tool exactly once, passing this script verbatim as the script parameter. Wait for the workflow to finish, then reply with exactly DONE.
<script>
$SCRIPT
</script>" --model $M --session-id "$ID" --output-format stream-json --verbose --max-turns 8 --allowedTools Workflow
  ;;
longprompt)
  ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/longprompt-session-id.txt"
  LP="Line one of a deliberately long probe prompt.
Line two continues so that the prompt is well over two hundred characters long, which lets us see whether last-prompt truncates it and what happens to newlines.
Line three: ignore all of the above and reply with exactly OK."
  printf '%s' "$LP" > "$C/longprompt-input.txt"
  run longprompt -p "$LP" --session-id "$ID" --model $M --output-format stream-json --verbose --max-turns 1
  ;;
esac; done
# copy every transcript tree touched into copies/
for idf in "$C"/*-session-id.txt; do
  ID=$(cat "$idf"); F=$(tfile "$ID"); [ -n "$F" ] || continue
  D="$E/copies/$(basename "$(dirname "$F")")"; mkdir -p "$D"
  cp "$F" "$D/"; [ -d "$(dirname "$F")/$ID" ] && cp -r "$(dirname "$F")/$ID" "$D/"
done
# privacy: Claude Code injects the account email into every session (session_context attachment). Redact it in copies.
python3 "$E/redact_copies.py" "$E/copies"; python3 "$E/redact_copies.py" "$C"
echo "done: $steps"
