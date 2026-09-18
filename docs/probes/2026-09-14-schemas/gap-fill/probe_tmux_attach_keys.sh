#!/bin/bash
# Shepherd gap-fill probe (2026-09-14):
#  A) a second tmux client attaching to a session that Runner.resize sized (spec 1141, 1991, 430):
#     window-size / aggressive-resize defaults, resize-window with and without a client, attach -f ignore-size, attach -r.
#  B) raw key bytes delivered to a pane through tmux (spec 1153, 1171-1173, 428):
#     send-keys -H, named keys, -l with escape text, paste-buffer -p (bracketed), writing to pane_tty.
# The pane program is keydump.py (raw mode, logs every byte it reads).
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh
# SAFETY: every tmux call passes -L shp-gap-att-inner / -L shp-gap-att-outer / -L shp-gap-keys;
#         the attach inside the outer pane is `env -u TMUX tmux -L shp-gap-att-inner attach ...`;
#         teardown is kill-server on those throwaway sockets only.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/tmux-attach-keys-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
{ echo "claude --version: $(claude --version)"; echo "tmux -V: $(tmux -V)"; uname -sr; } > "$OUT/versions.txt"
IN=shp-gap-att-inner; OU=shp-gap-att-outer; KS=shp-gap-keys
CLEAN=(env -i HOME=/root PATH=/usr/bin:/bin TERM=xterm-256color LANG=C.UTF-8)
F="$OUT/attach.txt"
run(){ echo "\$ $*" >> "$F"; "$@" >> "$F" 2>&1; echo "[rc=$?]" >> "$F"; }
state(){ echo "## state: $1" >> "$F"
  tmux -L $IN display-message -p -t '=shepherd_t1:' 'inner window=#{window_width}x#{window_height} pane=#{pane_width}x#{pane_height} session_attached=#{session_attached}' >> "$F" 2>&1
  echo "inner window-size option: $(tmux -L $IN show-options -wv -t '=shepherd_t1:' window-size 2>&1) (global: $(tmux -L $IN show-options -gwv window-size 2>&1)) aggressive-resize: $(tmux -L $IN show-options -gwv aggressive-resize 2>&1)" >> "$F"
  echo "inner list-clients: $(tmux -L $IN list-clients -F '#{client_tty} #{client_width}x#{client_height} flags=#{client_flags} session=#{client_session}' 2>&1 | tr '\n' ';')" >> "$F"
  echo "keydump SIGWINCH/start lines so far: $(grep -c . "$OUT/inner-keydump.jsonl" 2>/dev/null); last: $(grep -h 'sigwinch\|start' "$OUT/inner-keydump.jsonl" | tail -1)" >> "$F"
}

echo "## A. second client vs Runner.resize" > "$F"
run tmux -L $IN ls; run tmux -L $OU ls
run "${CLEAN[@]}" tmux -L $IN new-session -d -s shepherd_t1 -x 160 -y 45 "python3 $HERE/keydump.py $OUT/inner-keydump.jsonl"
sleep 1; state "A0 created -x 160 -y 45, no client"
run tmux -L $IN resize-window -t '=shepherd_t1:' -x 120 -y 40
sleep 1; state "A1 Runner.resize (resize-window -x 120 -y 40), no client"
run "${CLEAN[@]}" tmux -L $OU new-session -d -s outer1 -x 100 -y 30 "env -u TMUX tmux -L $IN attach -t =shepherd_t1"
sleep 2; state "A2 second client attached from a 100x30 terminal (plain attach)"
tmux -L $OU capture-pane -p -t '=outer1:' > "$OUT/A2-outer-client-view.txt"
run tmux -L $IN resize-window -t '=shepherd_t1:' -x 150 -y 50
sleep 1; state "A3 Runner.resize (-x 150 -y 50) while the 100x30 client is attached"
tmux -L $OU capture-pane -p -t '=outer1:' > "$OUT/A3-outer-client-view.txt"
run tmux -L $OU resize-window -t '=outer1:' -x 90 -y 25
sleep 1; state "A4 attached client's terminal resized to 90x25"
run tmux -L $IN set-option -w -t '=shepherd_t1:' window-size latest
sleep 1; state "A5 window-size set back to latest (the default) with the 90x25 client attached"
run tmux -L $IN resize-window -t '=shepherd_t1:' -x 150 -y 50
sleep 1; state "A6 Runner.resize (-x 150 -y 50) again after A5"
run tmux -L $OU kill-session -t '=outer1'
sleep 1; state "A7 the second client detached (its terminal closed)"
run tmux -L $IN set-option -w -t '=shepherd_t1:' window-size latest
run "${CLEAN[@]}" tmux -L $OU new-session -d -s outer2 -x 100 -y 30 "env -u TMUX tmux -L $IN attach -f ignore-size,read-only -t =shepherd_t1"
sleep 2; state "A8 client attached with -f ignore-size,read-only from 100x30, window-size=latest"
run tmux -L $IN resize-window -t '=shepherd_t1:' -x 130 -y 35
sleep 1; state "A9 Runner.resize (-x 130 -y 35) with the ignore-size client attached"
tmux -L $OU capture-pane -p -t '=outer2:' > "$OUT/A9-outer-client-view.txt"
run tmux -L $OU send-keys -t '=outer2:' -l 'RO'
sleep 1; echo "## A10 typed 'RO' into the read-only client; keydump lines with hex: $(grep -c hex "$OUT/inner-keydump.jsonl")" >> "$F"
run tmux -L $OU kill-server
run tmux -L $IN kill-server

# ---------------------------------------------------------------------------------------------
K="$OUT/keys.txt"
echo "## B. raw key delivery into a pane (keydump.py --bracketed)" > "$K"
krun(){ echo "\$ $*" >> "$K"; "$@" >> "$K" 2>&1; echo "[rc=$?]" >> "$K"; }
mark(){ echo "{\"marker\": \"$1\", \"t\": $(date +%s.%3N)}" >> "$OUT/keys-keydump.jsonl"; }
krun "${CLEAN[@]}" tmux -L $KS new-session -d -s shepherd_k1 -x 120 -y 30 "python3 $HERE/keydump.py $OUT/keys-keydump.jsonl --bracketed"
sleep 1
T='=shepherd_k1:'
mark "send-keys Escape";              krun tmux -L $KS send-keys -t $T Escape; sleep 0.6
mark "send-keys C-c";                 krun tmux -L $KS send-keys -t $T C-c; sleep 0.6
mark "send-keys Up Down Left Right";  krun tmux -L $KS send-keys -t $T Up Down Left Right; sleep 0.6
mark "send-keys Enter";               krun tmux -L $KS send-keys -t $T Enter; sleep 0.6
mark "send-keys BSpace Tab BTab";     krun tmux -L $KS send-keys -t $T BSpace Tab BTab; sleep 0.6
mark "send-keys -H 1b 5b 41 (raw ESC [ A)"; krun tmux -L $KS send-keys -t $T -H 1b 5b 41; sleep 0.6
mark "send-keys -H 03 (raw ETX)";     krun tmux -L $KS send-keys -t $T -H 03; sleep 0.6
mark "send-keys -H e2 9c 93 (UTF-8 check mark)"; krun tmux -L $KS send-keys -t $T -H e2 9c 93; sleep 0.6
mark "send-keys -l with literal ESC [ A text"; krun tmux -L $KS send-keys -t $T -l "$(printf '\033[A')"; sleep 0.6
mark "send-keys -l 'a\\nb' (literal LF)"; krun tmux -L $KS send-keys -t $T -l "$(printf 'a\nb')"; sleep 0.6
printf 'line one\nline two' > "$OUT/paste.txt"
krun tmux -L $KS load-buffer -b shpgap "$OUT/paste.txt"
mark "paste-buffer -p (bracketed, app enabled ?2004h)"; krun tmux -L $KS paste-buffer -p -b shpgap -t $T; sleep 0.6
mark "paste-buffer (no -p)";          krun tmux -L $KS paste-buffer -b shpgap -t $T; sleep 0.6
mark "send-keys -H with explicit 1b5b3230307e...1b5b3230317e"; krun tmux -L $KS send-keys -t $T -H 1b 5b 32 30 30 7e 68 69 1b 5b 32 30 31 7e; sleep 0.6
PTTY="$(tmux -L $KS display-message -p -t $T '#{pane_tty}')"
mark "printf XYZ > pane_tty ($PTTY)"; echo "\$ printf XYZ > $PTTY" >> "$K"; printf 'XYZ' > "$PTTY"; echo "[rc=$?]" >> "$K"; sleep 0.8
mark "end"
tmux -L $KS capture-pane -p -t $T > "$OUT/keys-pane-screen.txt"
krun tmux -L $KS kill-server
echo "## keydump log" >> "$K"; cat "$OUT/keys-keydump.jsonl" >> "$K"
cat "$F" "$K"
