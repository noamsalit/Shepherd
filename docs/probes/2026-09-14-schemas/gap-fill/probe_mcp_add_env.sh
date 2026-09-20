#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): `claude mcp add -e` argument parsing, in an isolated CLAUDE_CONFIG_DIR.
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_mcp_add_env.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="$HERE/mcp-add-env-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
echo "claude --version: $(claude --version)" > "$OUT/versions.txt"
D="$(mktemp -d /tmp/shp-gap-mcpenv-XXXXXX)"; mkdir -p "$D/cfg"
run(){ echo "\$ $*" >> "$OUT/mcp-add-env.txt"; ( cd "$D" && env -u CLAUDECODE CLAUDE_CONFIG_DIR="$D/cfg" "$@" ) >> "$OUT/mcp-add-env.txt" 2>&1; echo "[rc=$?]" >> "$OUT/mcp-add-env.txt"; }
run claude mcp add -s user -e SHP_X=1 shepherd -- /bin/true
run claude mcp add -s user shepherd -e SHP_X=1 -- /bin/true
run claude mcp get shepherd
python3 -c "import json,sys; d=json.load(open('$D/cfg/.claude.json')); print(json.dumps(d.get('mcpServers'), indent=1))" >> "$OUT/mcp-add-env.txt" 2>&1
cat "$OUT/mcp-add-env.txt"
