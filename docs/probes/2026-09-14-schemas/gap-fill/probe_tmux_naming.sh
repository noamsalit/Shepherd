#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): tmux session-name rewriting, -t target resolution,
# and $TMUX inheritance (spec 2344-2358, 1135; CLAUDE.md rules 3-4).
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh
# SAFETY: every tmux call passes -L shp-gap-name-a or -L shp-gap-name-b. No kill-server is ever run;
#         teardown is kill-session on each throwaway session by exact (=) name. Servers are started
#         under env -i so they do not inherit the caller's $TMUX.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/tmux-naming-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
{ echo "claude --version: $(claude --version)"; echo "tmux -V: $(tmux -V)"; uname -sr; } > "$OUT/versions.txt"
A=shp-gap-name-a; B=shp-gap-name-b
CLEAN=(env -i HOME=/root PATH=/usr/bin:/bin TERM=xterm-256color LANG=C.UTF-8)
F="$OUT/naming.txt"
run(){ echo "\$ $*" >> "$F"; "$@" >> "$F" 2>&1; echo "[rc=$?]" >> "$F"; }

echo "## precheck: both throwaway sockets must be empty" > "$F"
run tmux -L $A ls
run tmux -L $B ls

echo "## 1. create a session literally named 'shepherd' plus a window 'spike1' in it (stands in for the live session)" >> "$F"
run "${CLEAN[@]}" tmux -L $A new-session -d -s shepherd -x 80 -y 24 'sleep 100000'
run tmux -L $A new-window -d -t '=shepherd:' -n spike1 'sleep 100000'
echo "## 2. new-session with ':' and '.' in the name" >> "$F"
run tmux -L $A new-session -d -s 'shepherd:spike1' -x 80 -y 24 'sleep 100000'
run tmux -L $A new-session -d -s 'shepherd.dot1' -x 80 -y 24 'sleep 100000'
run tmux -L $A new-session -d -s 'shepherd_ok-1' -x 80 -y 24 'sleep 100000'
run tmux -L $A list-sessions -F '#{session_name}|#{session_id}|windows=#{session_windows}'
echo "## 3. has-session / display-message with the colon name as given by the caller" >> "$F"
run tmux -L $A has-session -t 'shepherd:spike1'
run tmux -L $A display-message -p -t 'shepherd:spike1' 'resolved: session=#{session_name} window=#{window_name} pane=#{pane_id}'
run tmux -L $A display-message -p -t '=shepherd:spike1' 'resolved(=): session=#{session_name} window=#{window_name} pane=#{pane_id}'
run tmux -L $A has-session -t '=shepherd_spike1'
run tmux -L $A display-message -p -t 'shepherd_spike1' 'resolved(rewritten name): session=#{session_name} window=#{window_name}'
run tmux -L $A display-message -p -t 'shepherd.dot1' 'resolved(dot, no =): session=#{session_name} window=#{window_name}'
run tmux -L $A display-message -p -t '=shepherd_dot1:' 'resolved(=shepherd_dot1:): session=#{session_name} window=#{window_name}'
echo "## 4. prefix matching without '=': 'shepherd_ok' is a prefix of 'shepherd_ok-1'" >> "$F"
run tmux -L $A display-message -p -t 'shepherd_ok' 'resolved(prefix): session=#{session_name}'
run tmux -L $A display-message -p -t '=shepherd_ok:' 'resolved(=prefix): session=#{session_name}'
run tmux -L $A display-message -p -t 'shep' 'resolved(ambiguous prefix): session=#{session_name}'
run tmux -L $A has-session -t '=shepherd_ok'
run tmux -L $A has-session -t 'shepherd_ok'
run tmux -L $A has-session -t 'shep'
run tmux -L $A display-message -p -t '=no_such_session:' 'nonexistent: session=#{session_name}'
run "${CLEAN[@]}" tmux -L $A display-message -p -t '=no_such_session:' 'nonexistent (env -i, TMUX unset): session=#{session_name}'
run tmux -L $A send-keys -t '=no_such_session:' -l 'x'

echo "## 5. \$TMUX inheritance: commands run INSIDE a pane of socket A" >> "$F"
run "${CLEAN[@]}" tmux -L $B new-session -d -s shepherd_other -x 80 -y 24 'sleep 100000'
cat > "$OUT/inpane.sh" <<'EOS'
#!/bin/sh
{
echo "inside pane: TMUX=$TMUX"
echo "--- bare 'tmux display-message -p #{socket_path}|#{session_name}' (no -L):"
tmux display-message -p '#{socket_path}|#{session_name}'
echo "--- bare 'tmux list-sessions -F #{session_name}' (no -L):"
tmux list-sessions -F '#{session_name}'
echo "--- 'tmux -L shp-gap-name-b list-sessions' (explicit -L):"
tmux -L shp-gap-name-b list-sessions -F '#{socket_path}|#{session_name}'
} > "$1" 2>&1
EOS
chmod +x "$OUT/inpane.sh"
run tmux -L $A new-window -d -t '=shepherd_ok-1:' -n probe "$OUT/inpane.sh $OUT/inpane-output.txt; sleep 100000"
sleep 2
echo "## inpane-output.txt" >> "$F"; cat "$OUT/inpane-output.txt" >> "$F"

echo "## teardown (kill-session by exact name only)" >> "$F"
for s in shepherd shepherd_spike1 shepherd_dot1 shepherd_ok-1; do run tmux -L $A kill-session -t "=$s"; done
run tmux -L $B kill-session -t '=shepherd_other'
sleep 1
run tmux -L $A ls
run tmux -L $B ls
cat "$F"
