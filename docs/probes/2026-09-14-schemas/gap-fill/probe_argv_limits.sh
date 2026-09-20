#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): limits on a brief passed as argv (companion to probe_argv.py).
#  1. the largest single argv word `tmux new-session` accepts (binary search; the pane runs `true`)
#  2. claude's own error for a positional prompt that starts with '-' (no model call: argument parsing fails)
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_argv_limits.sh
# SAFETY: tmux calls use -L shp-gap-argvlim only; teardown kill-server on that socket.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/argv-limits-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
{ echo "claude --version: $(claude --version)"; echo "tmux -V: $(tmux -V)"; uname -sr; echo "getconf ARG_MAX: $(getconf ARG_MAX)"; } > "$OUT/versions.txt"
S=shp-gap-argvlim
try(){ local n=$1; local a; a=$(head -c "$n" /dev/zero | tr '\0' 'x'); env -i PATH=/usr/bin:/bin tmux -L $S new-session -d -s "shepherd_l$n" true "$a" 2>&1; echo "rc=$?"; }
lo=1000; hi=20480
while [ $((hi-lo)) -gt 1 ]; do mid=$(((lo+hi)/2)); r=$(try $mid); if echo "$r" | grep -q "rc=0"; then lo=$mid; else hi=$mid; fi; done
{ echo "largest accepted single argv word (bytes): $lo"; echo "smallest rejected: $hi -> $(try $hi | tr '\n' ' ')"; echo "check $lo again -> $(try $lo | tr '\n' ' ')"; } > "$OUT/tmux-argv-limit.txt"
# the same limit for a command string (one word, run via sh -c)
try2(){ local n=$1; local a; a=$(head -c "$n" /dev/zero | tr '\0' 'y'); env -i PATH=/usr/bin:/bin tmux -L $S new-session -d -s "shepherd_s$n" "true $a" 2>&1; echo "rc=$?"; }
echo "single command string of $lo bytes -> $(try2 $lo | tr '\n' ' ')" >> "$OUT/tmux-argv-limit.txt"
echo "single command string of $hi bytes -> $(try2 $hi | tr '\n' ' ')" >> "$OUT/tmux-argv-limit.txt"
tmux -L $S kill-server 2>/dev/null
D="$(mktemp -d /tmp/shp-gap-argvlim-XXXXXX)"
( cd "$D" && env -u CLAUDECODE timeout 20 claude --model claude-haiku-4-5-20251001 "-starts with a dash DASH-BRIEF" </dev/null > "$OUT/claude-dash-brief.stdout" 2> "$OUT/claude-dash-brief.stderr"; echo "exit=$?" > "$OUT/claude-dash-brief.exit" )
cat "$OUT"/tmux-argv-limit.txt "$OUT"/claude-dash-brief.*
