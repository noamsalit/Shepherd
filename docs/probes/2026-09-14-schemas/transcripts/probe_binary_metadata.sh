#!/usr/bin/env bash
# Static probe: grep the installed Claude Code binary for the transcript metadata merge table and the pr-link writer.
# Usage: bash docs/probes/2026-09-14-schemas/transcripts/probe_binary_metadata.sh   (takes several minutes)
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"
B="$(readlink -f "$(command -v claude)")"
{ echo "claude_version: $(claude --version)"; echo "binary: $B"; echo "date_utc: $(date -u +%FT%TZ)"
  echo "# metadata merge-policy table(s)"
  LC_ALL=C timeout 500 grep -a -o '.\{0,500\}"agent-name":"last-wins".\{0,300\}' "$B" | head -3
  echo "# pr-link writer"
  LC_ALL=C timeout 500 grep -a -o '.\{0,80\}type:"pr-link".\{0,220\}' "$B" | head -3
} > "$C/binary-metadata-table.txt" 2>&1
