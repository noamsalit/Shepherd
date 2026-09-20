#!/usr/bin/env bash
# Shepherd linux-process-git probe: /proc shape of live claude processes, hook -> claude pid
# ownership, SO_PEERCRED over a 0600 UDS, and pid <-> session_id linkage (2026-09-14).
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh
#
# Four throwaway sessions (haiku, minimal turns, timeouts), all launched from a SYMLINKED path
# so /proc/<pid>/cwd, the hook payload cwd and git rev-parse can be compared:
#   A  claude -p --session-id <uuid>             (print mode, new session)
#   B  claude -p --resume <same uuid>            (print mode, resumed: how --resume shows in argv)
#   D  env -i ... claude -p --session-id <uuid3> (print mode, clean env: not a child of another Claude Code session)
#   C  claude --session-id <uuid2> --name ...    (interactive, inside tmux on a PRIVATE socket -L shp-lpg-proc)
# User-scope settings are never touched: hooks live in <tmpdir>/real/repo/.claude/settings.json
# with "enabledPlugins": {"cc10x@cc10x": false}. Every other claude process on the machine is
# only read (proc_snapshot.py stores a redacted shape of it). tmux teardown names the socket.
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
V="$(claude --version)"; M="$C/proc-meta.txt"
{ echo "claude_version: $V"; echo "date_utc: $(date -u +%FT%TZ)"; echo "uname: $(uname -srm)"; } > "$M"
HAIKU=claude-haiku-4-5-20251001
T="$(mktemp -d /tmp/shp-lpg-proc.XXXXXX)"; echo "tmpdir: $T" >> "$M"
mkdir -p "$T/real/repo/.claude" "$T/s"; chmod 700 "$T/s"
ln -s "$T/real" "$T/link"
git -C "$T/real/repo" init -q -b main && git -C "$T/real/repo" -c user.email=p@example.invalid -c user.name=probe commit -q --allow-empty -m init
LOG="$C/proc-hooks.jsonl"; : > "$LOG"; PEER="$C/proc-peercred.jsonl"; : > "$PEER"
SOCK="$T/s/hook.sock"
python3 - "$T/real/repo/.claude/settings.json" "$E/hook_capture.py" "$LOG" "$SOCK" "$V" <<'PY'
import json, sys
out, cap, log, sock, ver = sys.argv[1:]
evs = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"]
hooks = {e: [{"hooks": [{"type": "command", "timeout": 10,
          "command": f"SHP_CLAUDE_VERSION='{ver}' python3 {cap} {e} {log} {sock}"}]}] for e in evs}
json.dump({"enabledPlugins": {"cc10x@cc10x": False}, "hooks": hooks}, open(out, "w"), indent=1)
PY
cp "$T/real/repo/.claude/settings.json" "$C/proc-settings.json"
python3 "$E/sessiond_sim.py" "$SOCK" "$PEER" 300 & LST=$!
sleep 1
ls -la "$T/s" > "$C/proc-socket-ls.txt"; stat -c '%A %a %F %n' "$T/s" "$SOCK" >> "$C/proc-socket-ls.txt"
ID=$(python3 -c 'import uuid;print(uuid.uuid4())'); ID2=$(python3 -c 'import uuid;print(uuid.uuid4())')
echo "session_A_B: $ID" >> "$M"; echo "session_C: $ID2" >> "$M"
W="$T/link/repo"

nobody_probe() { # $1 pid $2 label : what a DIFFERENT uid can read of that claude process
  local p=$1 o="$C/proc-nobody-$2.txt" r rc; : > "$o"
  for f in cmdline comm stat status environ cwd exe fd; do
    case $f in
      cwd|exe) r=$(runuser -u nobody -- readlink -v "/proc/$p/$f" 2>&1 >/dev/null); rc=$? ;;
      fd) r=$(runuser -u nobody -- ls "/proc/$p/fd" 2>&1 >/dev/null); rc=$? ;;
      *) r=$(runuser -u nobody -- cat "/proc/$p/$f" 2>&1 >/dev/null); rc=$? ;;
    esac
    echo "$f: rc=$rc ${r:-readable}" | sed "s#/proc/$p/#/proc/<pid>/#g" >> "$o"
  done
}

# ---- A: print mode, new session
( cd "$W" && timeout 120 claude -p "Run the Bash command: sleep 12. Then reply with exactly OK." --model $HAIKU \
   --session-id "$ID" --max-turns 3 --allowedTools "Bash(sleep *)" --output-format stream-json --verbose \
   < /dev/null > "$C/proc-A-stream.jsonl" 2> "$C/proc-A-stderr.txt" ) &
RA=$!
sleep 9
python3 "$E/proc_snapshot.py" "$C/proc-A-snapshot.json" "$ID" "$T" > /dev/null
PA=$(python3 -c "import json;d=json.load(open('$C/proc-A-snapshot.json'));print(d['own'][0]['stat_named_fields']['1:pid'] if d['own'] else '')")
echo "A_claude_pid: $PA" >> "$M"
if [ -n "$PA" ]; then
  nobody_probe "$PA" A
  if [ -f /root/.claude/sessions/"$PA".json ]; then echo "A_registry_file: present"; python3 -m json.tool /root/.claude/sessions/"$PA".json > "$C/proc-A-registry.json"; else echo "A_registry_file: none"; fi >> "$M"
fi
# a Bash-tool child of claude, for contrast with a hook child
[ -n "$PA" ] && ps -o pid=,ppid=,comm=,args= --ppid "$PA" | sed -E 's/^ +//' > "$C/proc-A-children.txt"
wait $RA; echo "A_exit: $?" >> "$M"

# ---- B: print mode, --resume
( cd "$W" && timeout 120 claude -p "Run the Bash command: sleep 10. Then reply with exactly OK." --model $HAIKU \
   --resume "$ID" --max-turns 3 --allowedTools "Bash(sleep *)" --output-format stream-json --verbose \
   < /dev/null > "$C/proc-B-stream.jsonl" 2> "$C/proc-B-stderr.txt" ) &
RB=$!
sleep 9
python3 "$E/proc_snapshot.py" "$C/proc-B-snapshot.json" "$ID" "$T" > /dev/null
wait $RB; echo "B_exit: $?" >> "$M"

# ---- D: print mode launched with a CLEAN environment (env -i), i.e. not a child of any Claude Code session
ID3=$(python3 -c 'import uuid;print(uuid.uuid4())'); echo "session_D: $ID3" >> "$M"
( cd "$W" && env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TERM=xterm XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" PWD="$W" \
   timeout 120 claude -p "Run the Bash command: sleep 12. Then reply with exactly OK." --model $HAIKU \
   --session-id "$ID3" --max-turns 3 --allowedTools "Bash(sleep *)" --output-format stream-json --verbose \
   < /dev/null > "$C/proc-D-stream.jsonl" 2> "$C/proc-D-stderr.txt" ) &
RD=$!
sleep 9
python3 "$E/proc_snapshot.py" "$C/proc-D-snapshot.json" "$ID3" "$T" > /dev/null
PD=$(python3 -c "import json;d=json.load(open('$C/proc-D-snapshot.json'));print(d['own'][0]['stat_named_fields']['1:pid'] if d['own'] else '')")
echo "D_claude_pid: $PD" >> "$M"
if [ -n "$PD" ] && [ -f /root/.claude/sessions/"$PD".json ]; then echo "D_registry_file: present"; python3 -m json.tool /root/.claude/sessions/"$PD".json > "$C/proc-D-registry.json"; else echo "D_registry_file: none"; fi >> "$M"
wait $RD; echo "D_exit: $?" >> "$M"

# ---- C: interactive in tmux, private socket
SOCKT=shp-lpg-proc
tmux -L $SOCKT new-session -d -s lpgprobe -x 160 -y 50 \
  "cd '$W' && exec claude --model $HAIKU --session-id $ID2 --name 'shp lpg probe' --allowedTools 'Bash(sleep *)'"
sleep 8; tmux -L $SOCKT capture-pane -p -t lpgprobe > "$C/proc-C-pane-startup.txt"
tmux -L $SOCKT send-keys -t lpgprobe Down; sleep 1; tmux -L $SOCKT send-keys -t lpgprobe Enter; sleep 6
tmux -L $SOCKT send-keys -t lpgprobe -l "Run the Bash command sleep 20 and then reply OK"; sleep 1; tmux -L $SOCKT send-keys -t lpgprobe Enter
sleep 8
python3 "$E/proc_snapshot.py" "$C/proc-C-snapshot.json" "$ID2" "$T" > /dev/null
PC=$(python3 -c "import json;d=json.load(open('$C/proc-C-snapshot.json'));print(d['own'][0]['stat_named_fields']['1:pid'] if d['own'] else '')")
echo "C_claude_pid: $PC" >> "$M"
tmux -L $SOCKT list-panes -a -F '#{session_name}:#{window_id}.#{pane_id} pane_pid=#{pane_pid} pane_current_path=#{pane_current_path}' > "$C/proc-C-tmux-panes.txt"
if [ -n "$PC" ] && [ -f /root/.claude/sessions/"$PC".json ]; then
  python3 -m json.tool /root/.claude/sessions/"$PC".json > "$C/proc-C-registry.json"
  ls -la /root/.claude/sessions/ | grep -E " $PC\." | sed -E 's/[0-9a-f]{64}/<hash>/' > "$C/proc-C-registry-ls.txt"
fi
[ -n "$PC" ] && nobody_probe "$PC" C
sleep 20
tmux -L $SOCKT capture-pane -p -t lpgprobe > "$C/proc-C-pane-after.txt"
tmux -L $SOCKT send-keys -t lpgprobe -l "/exit"; sleep 1; tmux -L $SOCKT send-keys -t lpgprobe Enter; sleep 6
echo "C_registry_after_exit: $( [ -n "$PC" ] && [ -f /root/.claude/sessions/$PC.json ] && echo present || echo none)" >> "$M"
tmux -L $SOCKT kill-server 2>/dev/null

# ---- git view of the same symlinked cwd, for D22 prefix binding
{ echo "logical_cwd: $W"; echo "realpath: $(realpath "$W")";
  echo "rev-parse --show-toplevel (from logical cwd): $(cd "$W" && git rev-parse --show-toplevel)"; } > "$C/proc-cwd-forms.txt"
kill $LST 2>/dev/null; wait $LST 2>/dev/null
# redact account email if it leaked into anything we stored
sed -i -E 's/[A-Za-z0-9._%+-]+@(gmail|googlemail)\.com/<redacted-email>/g' "$C"/proc-* 2>/dev/null
echo "done: $(date -u +%FT%TZ)" >> "$M"
