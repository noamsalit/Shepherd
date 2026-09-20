#!/bin/bash
# Tier-2 binding probe: a stdio MCP server mounted into a headless `claude -p` via --mcp-config.
# Re-run: bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh [claude-binary]
# Writes to docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CAP="$HERE/../captures/stdio-mcp"; rm -rf "$CAP"; mkdir -p "$CAP"
CLAUDE_BIN="${1:-$(command -v claude)}"
VER="$("$CLAUDE_BIN" --version)"
T="$(mktemp -d /tmp/shp-mcp-XXXXXX)"; W="$T/work"; mkdir -p "$W/.claude"
sha256sum ~/.claude/settings.json > "$CAP/user-settings-sha256-before.txt"
H="$HERE/capture_hook.sh"; HL="$CAP/hooks.jsonl"
python3 - "$W/.claude/settings.json" "$H" "$HL" <<'PY'
import json, sys
path, hook, log = sys.argv[1:4]
evs = ["PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"]
cfg = {"enabledPlugins": {"cc10x@cc10x": False},
       "hooks": {e: [{"matcher": "", "hooks": [{"type": "command", "command": f"{hook} {e} {log}", "timeout": 10}]}] for e in evs}}
json.dump(cfg, open(path, "w"), indent=2)
PY
cat > "$T/mcp.json" <<JSON
{"mcpServers": {"probe": {"type": "stdio", "command": "python3", "args": ["$HERE/mcp_logger_server.py", "$CAP/mcp-wire.jsonl"], "env": {"PROBE_MARKER": "1"}}}}
JSON
cp "$W/.claude/settings.json" "$CAP/settings.json"; cp "$T/mcp.json" "$CAP/mcp.json"
PROMPT='Do these steps in order, one tool call per step, then reply DONE:
1. call mcp__probe__echo_note with text="hello" and count=2
2. call mcp__probe__fail_note with reason="probe"
3. call mcp__probe__rpc_error_note
4. call mcp__probe__danger_note with target="x"
5. call mcp__probe__echo_note with count=5 and NO text argument'
# Scrub env inherited from the calling Claude Code session; keep HOME/PATH so the local login is used.
SCRUB=$(env | cut -d= -f1 | grep -E '^(CLAUDE|ANTHROPIC|AI_AGENT)' | sed 's/^/-u /' | tr '\n' ' ')
echo "claude_bin=$CLAUDE_BIN" > "$CAP/meta.txt"; echo "claude_version=$VER" >> "$CAP/meta.txt"
echo "tmpdir=$T" >> "$CAP/meta.txt"; echo "scrubbed=$SCRUB" >> "$CAP/meta.txt"; echo "started=$(date -u +%FT%TZ)" >> "$CAP/meta.txt"
ARGS=(-p "$PROMPT" --model claude-haiku-4-5-20251001 --output-format stream-json --verbose
      --mcp-config "$T/mcp.json" --strict-mcp-config --tools "" --allowedTools "mcp__probe__echo_note,mcp__probe__fail_note,mcp__probe__rpc_error_note"
      --max-turns 10 --debug-file "$CAP/debug.log")
printf '%q ' "$CLAUDE_BIN" "${ARGS[@]}" >> "$CAP/meta.txt"; echo >> "$CAP/meta.txt"
( cd "$W" && env $SCRUB SHP_CLAUDE_VERSION="$VER" timeout 180 "$CLAUDE_BIN" "${ARGS[@]}" < /dev/null > "$CAP/stream.jsonl" 2> "$CAP/stderr.txt"; echo "exit=$?" >> "$CAP/meta.txt" )
echo "finished=$(date -u +%FT%TZ)" >> "$CAP/meta.txt"
sha256sum ~/.claude/settings.json > "$CAP/user-settings-sha256-after.txt"
grep -i -E "cc10x|plugin" "$CAP/debug.log" | head -20 > "$CAP/debug-cc10x-lines.txt"
grep -i "mcp" "$CAP/debug.log" | grep -i -E "probe|stdio|tool" | head -60 > "$CAP/debug-mcp-lines.txt"
rm -f "$CAP/latest"  # symlink the CLI drops next to --debug-file
echo "$CAP"
