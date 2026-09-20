#!/bin/bash
# Shepherd gap-fill probe (2026-09-14): tmux server started from a systemd --user unit.
#  Q1 (D14, spec 117/1139): which cgroup do the tmux server and the pane land in, and do they
#     survive `systemctl --user stop|restart` of the unit under KillMode=control-group (default),
#     KillMode=process, and when the server is launched into its own scope?
#  Q2 (D39, spec 143/2209-2219/547): does `claude` resolve on PATH and authenticate inside the
#     user manager's environment, and what environment does the tmux server hand to panes?
# Re-run:  bash docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh
# SAFETY: every tmux call uses -L shp-gap-sysd*; teardown is `tmux -L shp-gap-sysd* kill-server`;
#         units are transient, named shp-gap-*; only processes started here are signalled.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/systemd-tmux-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
VER="$(claude --version)"
{ echo "claude --version: $VER"; echo "tmux -V: $(tmux -V)"; echo "systemd: $(systemctl --version | head -1)"; uname -sr; } > "$OUT/versions.txt"
log(){ echo "$(date -u +%H:%M:%S.%3N) $*" | tee -a "$OUT/steps.log"; }
alive(){ [ -n "$1" ] && [ -d "/proc/$1" ] && echo "alive($(tr -d '\0' </proc/$1/comm 2>/dev/null))" || echo "dead"; }
cg(){ [ -n "$1" ] && cat "/proc/$1/cgroup" 2>/dev/null || echo "<no such pid>"; }

WD="$(mktemp -d /tmp/shp-gap-sysd-XXXXXX)"; echo "$WD" > "$OUT/tmpdir.txt"
mkdir -p "$WD/.claude"
cat > "$WD/.claude/settings.json" <<EOF
{"enabledPlugins":{"cc10x@cc10x":false},"remoteControlAtStartup":false,
 "hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"SHP_CLAUDE_VERSION='$VER' $HERE/capture_hook.sh SessionStart $OUT/hooks.jsonl"}]}],
          "SessionEnd":[{"hooks":[{"type":"command","command":"SHP_CLAUDE_VERSION='$VER' $HERE/capture_hook.sh SessionEnd $OUT/hooks.jsonl"}]}]}}
EOF

# ---------- Q2: user manager environment and claude inside a unit -------------------------
log "Q2 show-environment"
systemctl --user show-environment | awk -F= '{ if ($1=="PATH"||$1=="HOME"||$1=="LANG"||$1=="SHELL"||$1=="XDG_RUNTIME_DIR") print; else print $1"=<redacted>" }' > "$OUT/q2-user-manager-environment.txt"
log "Q2 transient oneshot: command -v claude; claude --version; claude auth status"
systemd-run --user --quiet --wait --pipe --collect --unit=shp-gap-env-check -p WorkingDirectory="$WD" \
  /bin/sh -c 'echo "PATH=$PATH"; echo "command -v claude -> $(command -v claude)"; echo "claude --version -> $(claude --version 2>&1)"; echo "TMUX=${TMUX-<unset>} CLAUDECODE=${CLAUDECODE-<unset>} TERM=${TERM-<unset>}"; claude auth status >/dev/null 2>&1; echo "claude auth status exit=$?"; cat /proc/self/cgroup' \
  > "$OUT/q2-unit-claude-resolve.txt" 2>&1; echo "systemd-run exit=$?" >> "$OUT/q2-unit-claude-resolve.txt"
UPATH="Environment=PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
log "Q2b same oneshot with -p $UPATH"
systemd-run --user --quiet --wait --pipe --collect --unit=shp-gap-env-check2 -p WorkingDirectory="$WD" -p "$UPATH" \
  /bin/sh -c 'echo "PATH=$PATH"; echo "command -v claude -> $(command -v claude)"; echo "claude --version -> $(claude --version 2>&1)"; claude auth status >/dev/null 2>&1; echo "claude auth status exit=$?"' \
  > "$OUT/q2b-unit-claude-resolve-with-path.txt" 2>&1; echo "systemd-run exit=$?" >> "$OUT/q2b-unit-claude-resolve-with-path.txt"
log "Q2c transient oneshot: one haiku -p turn from inside a unit, PATH set (auth works?)"
systemd-run --user --quiet --wait --pipe --collect --unit=shp-gap-auth-turn -p WorkingDirectory="$WD" -p RuntimeMaxSec=90 -p "$UPATH" \
  /bin/sh -c "claude -p --model claude-haiku-4-5-20251001 --output-format json --settings $WD/.claude/settings.json 'Reply with only the word PONG' | python3 -c 'import json,sys; d=json.load(sys.stdin); print({k: d.get(k) for k in (\"type\",\"subtype\",\"is_error\",\"result\",\"num_turns\")})'" \
  > "$OUT/q2c-unit-auth-turn.txt" 2>&1; echo "systemd-run exit=$?" >> "$OUT/q2c-unit-auth-turn.txt"

# ---------- Q1: tmux server inside a unit --------------------------------------------------
# $1=variant $2=socket $3=extra systemd-run props $4=how the server is started ("direct" | "scope") $5=action (stop|restart)
variant(){
  local V="$1" S="$2" PROPS="$3" HOW="$4" ACT="$5" UNIT="shp-gap-sessiond-$1"
  local F="$OUT/q1-$V.txt"
  log "Q1 variant=$V socket=$S props=[$PROPS] how=$HOW action=$ACT"
  local LAUNCH="tmux -L $S new-session -d -s shepherd_t1 -x 120 -y 40 -c $WD 'claude --model claude-haiku-4-5-20251001'; tmux -L $S new-window -d -t =shepherd_t1: -n sleeper 'sleep 100000'"
  if [ "$HOW" = scope ]; then
    LAUNCH="systemd-run --user --scope --quiet --unit=shp-gap-tmuxsrv-$V tmux -L $S new-session -d -s shepherd_t1 -x 120 -y 40 -c $WD 'claude --model claude-haiku-4-5-20251001'; tmux -L $S new-window -d -t =shepherd_t1: -n sleeper 'sleep 100000'"
  fi
  # the unit body stands in for sessiond: create the session, then stay running
  systemd-run --user --quiet --collect --unit="$UNIT" $PROPS -p WorkingDirectory="$WD" /bin/sh -c "$LAUNCH; exec sleep 100000"
  sleep 6
  local MAIN SRV PANE SLP
  MAIN="$(systemctl --user show "$UNIT" -p MainPID --value)"
  SRV="$(tmux -L "$S" display-message -p -t '=shepherd_t1:0' '#{pid}' 2>/dev/null)"
  PANE="$(tmux -L "$S" display-message -p -t '=shepherd_t1:0' '#{pane_pid}' 2>/dev/null)"
  SLP="$(tmux -L "$S" display-message -p -t '=shepherd_t1:sleeper' '#{pane_pid}' 2>/dev/null)"
  {
    echo "## variant $V  unit=$UNIT  props=[$PROPS]  server-launch=$HOW  action=$ACT"
    echo "## launch command (unit ExecStart /bin/sh -c): $LAUNCH; exec sleep 100000"
    echo "## systemctl --user show $UNIT"
    systemctl --user show "$UNIT" -p Id,ControlGroup,KillMode,KillSignal,SendSIGHUP,MainPID,ActiveState,SubState
    echo "## pids: unit MainPID=$MAIN tmux-server=$SRV pane0(claude)=$PANE pane1(sleep)=$SLP"
    echo "## /proc/<pid>/cgroup before $ACT"
    echo "unit-main:   $(cg "$MAIN")"
    echo "tmux-server: $(cg "$SRV")"
    echo "pane-claude: $(cg "$PANE")  comm=$(cat /proc/$PANE/comm 2>/dev/null)"
    echo "pane-sleep:  $(cg "$SLP")"
    echo "## pane process env (names + PATH/TERM/TMUX values) of pane-claude"
    [ -n "$PANE" ] && tr '\0' '\n' < "/proc/$PANE/environ" 2>/dev/null | awk -F= '{ if ($1=="PATH"||$1=="TERM"||$1=="TMUX"||$1=="TMUX_PANE"||$1=="HOME") print; else print $1"=<redacted>" }' | sort
    echo "## systemd-cgls of the unit cgroup"
    systemd-cgls --no-pager "/user.slice/user-0.slice/user@0.service/app.slice/$UNIT.service" 2>&1 | sed -E 's/[0-9a-f]{8}-[0-9a-f-]{27}/<uuid>/g' | head -20
    echo "## t=$(date -u +%H:%M:%S.%3N) systemctl --user $ACT $UNIT"
  } > "$F"
  systemctl --user "$ACT" "$UNIT" >> "$F" 2>&1; echo "systemctl exit=$?" >> "$F"
  sleep 4
  local MAIN2; MAIN2="$(systemctl --user show "$UNIT" -p MainPID --value 2>/dev/null)"
  {
    echo "## after $ACT (+4s)"
    systemctl --user show "$UNIT" -p ActiveState,SubState,MainPID,NRestarts 2>&1
    echo "unit-main(old $MAIN): $(alive "$MAIN")   unit-main(new $MAIN2): $(alive "$MAIN2")"
    echo "tmux-server $SRV: $(alive "$SRV")"
    echo "pane-claude $PANE: $(alive "$PANE")"
    echo "pane-sleep  $SLP: $(alive "$SLP")"
    echo "## tmux -L $S list-sessions"
    tmux -L "$S" list-sessions 2>&1
    echo "## tmux -L $S list-panes -a -F"
    tmux -L "$S" list-panes -a -F '#{session_name}:#{window_name} pane_pid=#{pane_pid} dead=#{pane_dead}' 2>&1
    echo "## journal (unit, last lines)"
    journalctl --user -u "$UNIT" --no-pager -n 8 -o short-iso 2>&1 | sed -E 's/^[^ ]+ [^ ]+ /<ts> <host> /'
  } >> "$F"
  # teardown (only this probe's socket and unit)
  tmux -L "$S" kill-server >/dev/null 2>&1
  systemctl --user stop "$UNIT" >/dev/null 2>&1; systemctl --user stop "shp-gap-tmuxsrv-$V.scope" >/dev/null 2>&1
  systemctl --user reset-failed "$UNIT" >/dev/null 2>&1
  sleep 1
  echo "## teardown: tmux -L $S ls -> $(tmux -L "$S" ls 2>&1)" >> "$F"
}

variant nopath    shp-gap-sysd-n ""                                     direct stop
variant cgstop    shp-gap-sysd-a "-p $UPATH"                           direct stop
variant cgrestart shp-gap-sysd-b "-p $UPATH"                           direct restart
variant procstop  shp-gap-sysd-c "-p $UPATH -p KillMode=process"       direct stop
variant scopestop shp-gap-sysd-d "-p $UPATH"                           scope  stop
log "done -> $OUT"
