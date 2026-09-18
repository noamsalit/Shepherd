#!/usr/bin/env bash
# Shepherd linux-process-git probe: is /proc/<pid>/comm always "claude"? Launch the SAME binary by its versioned
# full path (/root/.local/share/claude/versions/<v>) instead of the `claude` symlink and read comm/exe/argv0 (2026-09-14).
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_comm_fullpath.sh
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
O="$C/comm-fullpath.txt"; V="$(claude --version)"
BIN="$(readlink -f "$(command -v claude)")"
T="$(mktemp -d /tmp/shp-lpg-comm.XXXXXX)"; mkdir -p "$T/.claude"; echo '{"enabledPlugins":{"cc10x@cc10x":false}}' > "$T/.claude/settings.json"
{ echo "claude_version: $V"; echo "date_utc: $(date -u +%FT%TZ)"; echo "symlink: $(command -v claude) -> $BIN"; } > "$O"
ID=$(python3 -c 'import uuid;print(uuid.uuid4())')
( cd "$T" && timeout 90 "$BIN" -p "Run the Bash command: sleep 8. Then reply with exactly OK." --model claude-haiku-4-5-20251001 \
   --session-id "$ID" --max-turns 3 --allowedTools "Bash(sleep *)" < /dev/null > /dev/null 2>&1 ) &
R=$!
sleep 6
for p in $(pgrep -f -- "--session-id $ID"); do
  [ "$(readlink /proc/$p/exe 2>/dev/null)" = "$BIN" ] || continue
  { echo "pid: $p"; echo "comm: $(cat /proc/$p/comm)"; echo "status Name: $(awk -F'\t' '/^Name:/{print $2}' /proc/$p/status)";
    echo "stat field 2: $(sed -E 's/^[0-9]+ \((.*)\) .*/\1/' /proc/$p/stat)"; echo "exe: $(readlink /proc/$p/exe)";
    echo "argv0: $(tr '\0' '\n' < /proc/$p/cmdline | head -1)";
    echo "registry_file: $( [ -f /root/.claude/sessions/$p.json ] && echo present || echo none)"; } >> "$O"
done
wait $R; echo "exit: $?" >> "$O"
rm -rf "$T"
