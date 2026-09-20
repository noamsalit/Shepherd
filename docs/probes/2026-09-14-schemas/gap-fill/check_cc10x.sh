#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): did the user-scope cc10x plugin's hooks fire in the gap-fill runs that used the
# real ~/.claude config (real-API runs)? Counts only: occurrences of "cc10x" and the Stop hookCount values in the
# throwaway transcripts of those runs. (Mock runs used an isolated CLAUDE_CONFIG_DIR where the plugin is not installed.)
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/check_cc10x.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="$HERE/cc10x-check-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
echo "claude --version: $(claude --version)" > "$OUT/versions.txt"
cd /root/.claude/projects || exit 1
for f in ./-tmp-shp-gap-acr-*/*.jsonl ./-tmp-shp-gap-int-real-*/*.jsonl ./-tmp-shp-gap-xver-*/*.jsonl ./-tmp-shp-gap-sysd-*/*.jsonl; do
  [ -f "$f" ] || continue
  echo "$f cc10x_occurrences=$(grep -c cc10x "$f") stop_hook_summary_hookCount=[$(grep -o '"hookCount":[0-9]*' "$f" | sort | uniq -c | tr -s ' ' | tr '\n' ';')]"
done > "$OUT/counts.txt"
cat "$OUT/counts.txt"
