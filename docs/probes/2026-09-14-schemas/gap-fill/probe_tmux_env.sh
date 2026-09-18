#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): which environment does a new tmux pane get?
# The server's (from whoever started it first) or the calling client's? And does new-session -e override it?
# Matters for LocalRunner: sessiond starts sessions with per-session env (CLAUDE_CONFIG_DIR, credentials, PATH).
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_env.sh
# SAFETY: -L shp-gap-env only; teardown kill-server on that socket.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/tmux-env-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
{ echo "claude --version: $(claude --version)"; echo "tmux -V: $(tmux -V)"; uname -sr; } > "$OUT/versions.txt"
S=shp-gap-env; F="$OUT/env.txt"
P='sh -c "echo SHP_PROBE_VAR=\${SHP_PROBE_VAR-<unset>} PATH=\$PATH TMUX=\${TMUX-<unset>}; sleep 100000"'
run(){ echo "\$ $*" >> "$F"; "$@" >> "$F" 2>&1; echo "[rc=$?]" >> "$F"; }
echo "## precheck" > "$F"; run tmux -L $S ls
echo "## 1. first client starts the server with SHP_PROBE_VAR=from-first-client" >> "$F"
run env -i PATH=/usr/bin:/bin SHP_PROBE_VAR=from-first-client tmux -L $S new-session -d -s shepherd_e1 "$P"
echo "## 2. second client, different env (SHP_PROBE_VAR=from-second-client, PATH=/opt/x:/usr/bin:/bin), no -e" >> "$F"
run env -i PATH=/opt/x:/usr/bin:/bin SHP_PROBE_VAR=from-second-client tmux -L $S new-session -d -s shepherd_e2 "$P"
echo "## 3. second client with new-session -e SHP_PROBE_VAR=from-dash-e -e PATH=/opt/y:/usr/bin:/bin" >> "$F"
run env -i PATH=/usr/bin:/bin tmux -L $S new-session -d -s shepherd_e3 -e SHP_PROBE_VAR=from-dash-e -e PATH=/opt/y:/usr/bin:/bin "$P"
echo "## 4. set-environment -g after the server started, then a new session without -e" >> "$F"
run tmux -L $S set-environment -g SHP_PROBE_VAR from-set-environment-g
run env -i PATH=/usr/bin:/bin tmux -L $S new-session -d -s shepherd_e4 "$P"
sleep 1
for s in shepherd_e1 shepherd_e2 shepherd_e3 shepherd_e4; do echo "## pane output of $s: $(tmux -L $S capture-pane -p -t "=$s:" | grep -v '^$')" >> "$F"; done
echo "## update-environment (server default)" >> "$F"; run tmux -L $S show-options -g update-environment
run tmux -L $S kill-server
cat "$F"
