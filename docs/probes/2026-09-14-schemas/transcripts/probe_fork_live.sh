#!/usr/bin/env bash
# Re-runnable probe for spec §9 ask() (D13): fork a LIVE interactive session while it is mid-turn and check
#  (1) the fork answers from the target's context, (2) the target's transcript gains no fork entries,
#  (3) ids/files of the fork. Target runs in tmux on a PRIVATE socket (-L shp-schemas-fork), haiku, torn down after.
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_fork_live.sh
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
V="$(claude --version)"; M="$C/forklive-meta.txt"; { echo "claude_version: $V"; echo "date_utc: $(date -u +%FT%TZ)"; } > "$M"
SOCK=shp-schemas-fork; MODEL=claude-haiku-4-5-20251001
W="$(mktemp -d /tmp/shp-schemas-fork.XXXXXX)/work"; mkdir -p "$W/.claude"
echo '{"enabledPlugins":{"cc10x@cc10x":false},"permissions":{"allow":["Bash(python3 -c *)"]}}' > "$W/.claude/settings.json"
ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "$ID" > "$C/forklive-target-session-id.txt"; echo "cwd: $W" >> "$M"
tmux -L $SOCK new-session -d -s t -x 160 -y 50 -c "$W" "claude --model $MODEL --session-id $ID"
sleep 8; tmux -L $SOCK send-keys -t t Down; sleep 1; tmux -L $SOCK send-keys -t t Enter; sleep 6   # accept trust dialog
say() { tmux -L $SOCK send-keys -t t -l "$1"; sleep 1; tmux -L $SOCK send-keys -t t Enter; }
say "The codeword for this session is PINEAPPLE-42. Reply with exactly OK."; sleep 15
say "Run this exact Bash command in the foreground (not in background): python3 -c \"import time; time.sleep(45)\" -- then reply with exactly DONE."; sleep 12
TF=$(ls /root/.claude/projects/*/"$ID".jsonl | head -1); echo "target_file: $TF" >> "$M"
echo "target_lines_before_fork: $(wc -l < "$TF")" >> "$M"
tmux -L $SOCK capture-pane -p -t t > "$C/forklive-pane-before-fork.txt"
(cd "$W" && timeout 120 claude -p "What is the codeword for this session? Reply with the codeword only." --resume "$ID" --fork-session \
   --model $MODEL --output-format json < /dev/null > "$C/forklive-fork-stdout.json" 2> "$C/forklive-fork-stderr.txt"); echo "fork_exit: $?" >> "$M"
echo "target_lines_right_after_fork: $(wc -l < "$TF")" >> "$M"
FID=$(python3 -c "import json;print(json.load(open('$C/forklive-fork-stdout.json'))['session_id'])"); echo "fork_session_id: $FID" >> "$M"
sleep 45
echo "target_lines_after_target_turn: $(wc -l < "$TF")" >> "$M"
tmux -L $SOCK capture-pane -p -t t > "$C/forklive-pane-after.txt"
say "/exit"; sleep 5; tmux -L $SOCK kill-server 2>/dev/null
FF=$(ls /root/.claude/projects/*/"$FID".jsonl | head -1); echo "fork_file: $FF" >> "$M"
python3 - "$TF" "$FF" "$ID" "$FID" >> "$M" <<'PY'
import json, sys
tf, ff, tid, fid = sys.argv[1:5]
T = [json.loads(l) for l in open(tf)]; F = [json.loads(l) for l in open(ff)]
print('target_entries_mentioning_fork_id:', sum(fid in json.dumps(x) for x in T))
print('target_entries_with_fork_question:', sum('What is the codeword' in json.dumps(x) for x in T))
print('fork_sessionId_values:', sorted({x.get('sessionId') for x in F if x.get('sessionId')}))
tu = {x['uuid'] for x in T if 'uuid' in x}; fu = [x['uuid'] for x in F if 'uuid' in x]
print('fork_uuids_total:', len(fu), 'shared_with_target:', sum(u in tu for u in fu))
print('fork_contains_target_turn2_prompt:', any('time.sleep(45)' in json.dumps(x) for x in F if x.get('type') == 'user'))
PY
mkdir -p "$E/copies/$(basename "$(dirname "$TF")")"; cp "$TF" "$FF" "$E/copies/$(basename "$(dirname "$TF")")/"
python3 "$E/redact_copies.py" "$E/copies"; python3 "$E/redact_copies.py" "$C"
