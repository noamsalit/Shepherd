#!/bin/bash
# Hook capture for the agent-sdk-mcp probe. Usage: capture_hook.sh <EventName> <log.jsonl>
# Appends one JSONL line: event name, UTC timestamp, claude --version (from env set by the runner),
# the /proc parent chain, and the raw stdin payload inserted verbatim. Always exits 0.
ev="$1"; log="$2"; epoch="$EPOCHREALTIME"
raw="$(cat)"
TZ=UTC printf -v ts '%(%Y-%m-%dT%H:%M:%S)T' "${epoch%.*}"; ts="$ts.${epoch#*.}"; ts="${ts:0:23}Z"
anc=""; pid=$$
for i in 1 2 3 4 5 6 7 8 9 10; do
  [ -r "/proc/$pid/status" ] || break
  comm=$(awk -F'\t' '/^Name:/{print $2}' /proc/$pid/status); ppid=$(awk -F'\t' '/^PPid:/{print $2}' /proc/$pid/status)
  [ -n "$anc" ] && anc+=","; anc+="{\"pid\":$pid,\"comm\":\"$comm\",\"ppid\":$ppid}"
  [ "$ppid" -le 1 ] && break; pid=$ppid
done
printf '{"_event":"%s","_captured_at":"%s","_claude_version":"%s","_ancestry":[%s],"payload":%s}\n' \
  "$ev" "$ts" "${SHP_CLAUDE_VERSION:-unknown}" "$anc" "$raw" >> "$log"
exit 0
