#!/bin/bash
# Shepherd hook-schema probe capture (2026-09-14).
# Usage (as a hook command):  capture_hook.sh <EventName> <log.jsonl>
# Appends ONE JSONL line:
#   {"_event":..., "_captured_at":..., "_epoch":..., "_claude_version":..., "_hook_pid":...,
#    "_claude_pid":..., "_ancestry":[{"pid","comm","ppid"},...], "payload": <raw stdin>}
# The raw stdin is inserted byte-for-byte (no parsing), so a payload that is not
# valid JSON would show up as a broken line rather than being silently fixed.
# Deliberately fork-free (bash builtins only: read, printf, $EPOCHREALTIME) because
# in -p mode Claude Code exits a few ms after dispatching StopFailure/SessionEnd and
# kills hook children that are still running. Always exits 0.
ev="$1"; log="$2"; TZ=UTC
epoch="$EPOCHREALTIME"
raw=""
while IFS= read -r -d '' chunk || [ -n "$chunk" ]; do raw+="$chunk"; chunk=""; done
nl=false
while [ "${raw: -1}" = $'\n' ]; do raw="${raw%$'\n'}"; nl=true; done
printf -v ts '%(%Y-%m-%dT%H:%M:%S)T' "${epoch%.*}"
ts="$ts.${epoch#*.}"; ts="${ts:0:23}Z"
anc=""; cpid="null"; pid=$$; i=0
while [ "$i" -lt 14 ] && [ -r "/proc/$pid/status" ]; do
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
printf '{"_event":"%s","_captured_at":"%s","_epoch":%s,"_claude_version":"%s","_hook_pid":%s,"_claude_pid":%s,"_ancestry":[%s],"_raw_trailing_newline":%s,"payload":%s}\n' \
  "$ev" "$ts" "$epoch" "${SHP_CLAUDE_VERSION:-unknown}" "$$" "$cpid" "$anc" "$nl" "$raw" >> "$log"
exit 0
