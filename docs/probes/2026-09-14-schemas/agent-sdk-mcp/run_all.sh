#!/bin/bash
# Re-run every agent-sdk-mcp probe from scratch. ~6 min wall, a few cents of Haiku on the local seat.
# Re-run: bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/run_all.sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"; CAP="$HERE/captures"; mkdir -p "$CAP"
T="$(mktemp -d /tmp/shp-sdk-XXXXXX)"; echo "$T" > "$CAP/tmpdir-path.txt"
sha256sum ~/.claude/settings.json > "$CAP/user-settings-sha256-before.txt"
# 1) throwaway venv (this python has no ensurepip, so bootstrap pip with get-pip.py)
python3 -m venv --without-pip "$T/venv"
curl -sS -o "$T/get-pip.py" https://bootstrap.pypa.io/get-pip.py
"$T/venv/bin/python" "$T/get-pip.py" -q
"$T/venv/bin/pip" install -q claude-agent-sdk
"$T/venv/bin/pip" freeze > "$CAP/pip-freeze.txt"
# 2) auth context for D30 (names and existence only, never values)
{
  echo "date: $(date -u +%FT%TZ)"
  echo "PATH claude --version: $(claude --version)"
  echo "~/.claude/.credentials.json exists: $([ -f ~/.claude/.credentials.json ] && echo yes || echo no)"
  echo "ANTHROPIC_* env names in the calling shell: $(env | cut -d= -f1 | grep '^ANTHROPIC' | tr '\n' ' ')"
  echo "(master_probe.py additionally deletes every CLAUDE*/ANTHROPIC*/AI_AGENT var before spawning the CLI)"
} > "$CAP/auth-context.txt"
# 3) introspection of the installed package
"$T/venv/bin/python" "$HERE/introspect_sdk.py" "$CAP/introspect"
# 4) live master scenarios (bundled CLI), plus `locked` against the PATH claude
for s in basic tools_empty locked resume interrupt isolation slow_approval interrupt_pending_approval deny resume_other_cwd; do
  timeout 300 "$T/venv/bin/python" "$HERE/master_probe.py" "$s" "$CAP" "$T"
done
timeout 300 "$T/venv/bin/python" "$HERE/master_probe.py" locked "$CAP" "$T" --cli "$(command -v claude)"
# 5) tier-2 stdio MCP binding in headless claude
bash "$HERE/stdio/run_stdio_probe.sh"
sha256sum ~/.claude/settings.json > "$CAP/user-settings-sha256-after.txt"
# 6) privacy pass, then render SECTION.md from the captures
python3 "$HERE/redact_captures.py" "$CAP"
python3 "$HERE/build_section.py"
