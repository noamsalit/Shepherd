#!/usr/bin/env bash
# Re-runnable probe: registry file ~/.claude/sessions/<pid>.json and `claude agents --json` for an INTERACTIVE
# throwaway session (print-mode sessions are not registered, see probe_registry.sh).
# Runs claude (haiku) inside tmux on a PRIVATE socket (-L shp-schemas-tx); tears down only that socket.
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_registry_interactive.sh
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
V="$(claude --version)"; M="$C/regint-meta.txt"; { echo "claude_version: $V"; echo "date_utc: $(date -u +%FT%TZ)"; } > "$M"
SOCK=shp-schemas-tx
W="$(mktemp -d /tmp/shp-schemas-regint.XXXXXX)/work"; mkdir -p "$W/.claude"
echo '{"enabledPlugins":{"cc10x@cc10x":false}}' > "$W/.claude/settings.json"
ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/regint-session-id.txt"; echo "cwd: $W" >> "$M"
tmux -L $SOCK new-session -d -s probe -x 160 -y 50 -c "$W" "claude --model claude-haiku-4-5-20251001 --session-id $ID --name 'shp regint probe'"
snap() { # label
  local f; f=$(grep -l "\"sessionId\": *\"$ID\"" /root/.claude/sessions/*.json 2>/dev/null | head -1)
  echo "$1 registry_file: ${f:-none}" >> "$M"
  [ -n "$f" ] && python3 -m json.tool "$f" > "$C/regint-registry-$1.json"
  timeout 30 claude agents --json 2>>"$C/regint-agents-stderr.txt" | python3 -c "
import json,sys
d=json.load(sys.stdin); own=[x for x in d if x.get('sessionId')=='$ID']
json.dump({'total_entries':len(d),'own':own}, open('$C/regint-agents-$1.json','w'), indent=1)"
  tmux -L $SOCK capture-pane -p -t probe > "$C/regint-pane-$1.txt"
}
sleep 8; snap startup
tmux -L $SOCK send-keys -t probe Down; sleep 1; tmux -L $SOCK send-keys -t probe Enter; sleep 6; snap after-trust
tmux -L $SOCK send-keys -t probe -l "Run the Bash command sleep 20 and then reply OK"; sleep 1; tmux -L $SOCK send-keys -t probe Enter
sleep 7; snap busy
sleep 25; snap after-turn
tmux -L $SOCK send-keys -t probe -l "/exit"; sleep 1; tmux -L $SOCK send-keys -t probe Enter; sleep 5
F=$(grep -l "\"sessionId\": *\"$ID\"" /root/.claude/sessions/*.json 2>/dev/null | head -1); echo "after_exit registry_file: ${F:-none}" >> "$M"
tmux -L $SOCK kill-server 2>/dev/null
sed -i -E 's/[A-Za-z0-9._%+-]+@(gmail|googlemail)\.com/<redacted-email>/g' "$C"/regint-* 2>/dev/null
# copy the throwaway transcript and redact account identifiers
TF=$(ls /root/.claude/projects/*/"$ID".jsonl 2>/dev/null | head -1)
[ -n "$TF" ] && { mkdir -p "$E/copies/$(basename "$(dirname "$TF")")"; cp "$TF" "$E/copies/$(basename "$(dirname "$TF")")/"; }
python3 "$E/redact_copies.py" "$E/copies"; python3 "$E/redact_copies.py" "$C"
