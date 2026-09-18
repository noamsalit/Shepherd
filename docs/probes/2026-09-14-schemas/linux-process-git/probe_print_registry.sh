#!/usr/bin/env bash
# Shepherd linux-process-git probe: does a PRINT-MODE (`claude -p`) session write ~/.claude/sessions/<pid>.json,
# and does the answer depend on --output-format or on inheriting a parent Claude Code session's env? (2026-09-14)
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_print_registry.sh
#
# Four throwaway -p runs (haiku, one Bash sleep, timeout 90): {text, stream-json} x {inherited env, env -i}.
# For each, 7 s in, record whether the registry file for that claude pid exists and copy it (own session only).
# No hooks, no settings changes; cc10x disabled in <tmpdir>/.claude/settings.json.
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
M="$C/print-registry.txt"; V="$(claude --version)"
{ echo "claude_version: $V"; echo "date_utc: $(date -u +%FT%TZ)"; } > "$M"
T="$(mktemp -d /tmp/shp-lpg-preg.XXXXXX)"; mkdir -p "$T/.claude"; echo '{"enabledPlugins":{"cc10x@cc10x":false}}' > "$T/.claude/settings.json"
echo "tmpdir: $T" >> "$M"
for fmt in text stream-json; do
  for envmode in inherited clean; do
    ID=$(python3 -c 'import uuid;print(uuid.uuid4())')
    args=(claude -p "Run the Bash command: sleep 10. Then reply with exactly OK." --model claude-haiku-4-5-20251001
          --session-id "$ID" --max-turns 3 --allowedTools "Bash(sleep *)" --output-format "$fmt")
    [ "$fmt" = stream-json ] && args+=(--verbose)
    if [ "$envmode" = clean ]; then
      ( cd "$T" && env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TERM=xterm XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" timeout 90 "${args[@]}" < /dev/null > /dev/null 2>&1 ) &
    else
      ( cd "$T" && timeout 90 "${args[@]}" < /dev/null > /dev/null 2>&1 ) &
    fi
    R=$!
    sleep 7
    P=$(grep -l "\"sessionId\": *\"$ID\"" /root/.claude/sessions/*.json 2>/dev/null | head -1)
    PID=$(pgrep -f -- "--session-id $ID" | while read -r p; do [ "$(cat /proc/$p/comm 2>/dev/null)" = claude ] && echo "$p"; done | head -1)
    echo "run fmt=$fmt env=$envmode session=$ID claude_pid=${PID:-none} registry_file=${P:-none}" >> "$M"
    [ -n "$P" ] && python3 -m json.tool "$P" > "$C/print-registry-$fmt-$envmode.json"
    wait $R; echo "  exit=$?" >> "$M"
    echo "  after_exit_registry_file=$( [ -n "$P" ] && [ -f "$P" ] && echo present || echo none)" >> "$M"
  done
done
echo "done: $(date -u +%FT%TZ)" >> "$M"
