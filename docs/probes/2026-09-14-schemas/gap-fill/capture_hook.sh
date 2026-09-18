#!/bin/bash
# Shepherd gap-fill probe: hook capture (2026-09-14; copied from tmux-tui/capture_hook.sh).
# Usage as a hook command:  capture_hook.sh <EventName> <log.jsonl>
# Appends one JSONL line:
#   {"_event", "_captured_at" (UTC, ours), "_epoch", "_claude_version", "_hook_pid",
#    "_claude_pid", "_ancestry":[{pid,comm,ppid}...], "payload": <raw stdin, byte-for-byte>}
# Fork-free (bash builtins only) so it completes even when claude is exiting
# (SessionEnd on /exit or on SIGHUP from a killed pane). Always exits 0.
ev="$1"; log="$2"; TZ=UTC
epoch="$EPOCHREALTIME"
raw=""
while IFS= read -r -d '' chunk || [ -n "$chunk" ]; do raw+="$chunk"; chunk=""; done
while [ "${raw: -1}" = $'\n' ]; do raw="${raw%$'\n'}"; done
[ -z "$raw" ] && raw='null'
printf -v ts '%(%Y-%m-%dT%H:%M:%S)T' "${epoch%.*}"
ts="$ts.${epoch#*.}"; ts="${ts:0:23}Z"
anc=""; cpid="null"; pid=$$; i=0
while [ "$i" -lt 16 ] && [ -r "/proc/$pid/status" ]; do
  comm=""; ppid=""
  while IFS=$'\t' read -r k v; do
    case "$k" in
      Name:) comm="${v//[\"\\]/}" ;;
      PPid:) ppid="$v"; break ;;
    esac
  done < "/proc/$pid/status"
  [ -n "$anc" ] && anc+=","
  anc+="{\"pid\":$pid,\"comm\":\"$comm\",\"ppid\":${ppid:-0}}"
  if [ "$cpid" = "null" ] && [ "$comm" = "claude" ]; then cpid=$pid; fi
  { [ -z "$ppid" ] || [ "$ppid" -le 1 ]; } && break
  pid=$ppid; i=$((i+1))
done
printf '{"_event":"%s","_captured_at":"%s","_epoch":%s,"_claude_version":"%s","_hook_pid":%s,"_claude_pid":%s,"_ancestry":[%s],"payload":%s}\n' \
  "$ev" "$ts" "$epoch" "${SHP_CLAUDE_VERSION:-unknown}" "$$" "$cpid" "$anc" "$raw" >> "$log"
exit 0
