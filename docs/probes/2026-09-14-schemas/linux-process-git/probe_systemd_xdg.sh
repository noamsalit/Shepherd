#!/usr/bin/env bash
# Shepherd linux-process-git probe: systemd USER manager, one transient unit (Restart= behaviour,
# journal), lingering, and XDG base-directory values in this shell vs under the user manager (2026-09-14).
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh
#
# Safety: writes NO unit files and does NOT enable linger. Starts exactly ONE transient unit
# (systemd-run --user, a short sleep that exits 1 under Restart=always), observes it, then stops and
# reset-fails it so it disappears.
# NOTE (observed 2026-09-14): systemd itself expands ${VAR-...} and $$ inside ExecStart before /bin/sh sees them,
# so the "start ..." journal line prints empty values plus an "Invalid environment variable name" warning.
# That quirk is kept deliberately so a re-run reproduces the capture; the "env names:" line and
# `systemctl --user show-environment` carry the real XDG facts. In a real unit file write $${VAR} to defer to the shell.
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
O="$C/systemd-xdg.txt"
exec > "$O" 2>&1
echo "claude_version: $(claude --version)"; echo "date_utc: $(date -u +%FT%TZ)"; echo "id: $(id)"
echo; echo "## systemd --version"; systemctl --version | head -2
echo; echo "## this shell: XDG values"
for v in XDG_RUNTIME_DIR XDG_DATA_HOME XDG_CONFIG_HOME XDG_STATE_HOME XDG_CACHE_HOME DBUS_SESSION_BUS_ADDRESS XDG_SESSION_ID XDG_SESSION_CLASS; do
  echo "$v=${!v-<unset>}"; done
echo "shell_is_login: $(shopt -q login_shell && echo yes || echo no)"
echo; echo "## python resolution of the spec's §15 paths (XDG default when unset)"
python3 -c '
import os
h=os.path.expanduser("~")
for k,d in (("XDG_DATA_HOME",h+"/.local/share"),("XDG_CONFIG_HOME",h+"/.config")):
    print(k, "->", os.environ.get(k) or d, "(env)" if os.environ.get(k) else "(default)")
print("XDG_RUNTIME_DIR ->", os.environ.get("XDG_RUNTIME_DIR", "<unset: no default in the spec>"))'
echo; echo "## /run/user/<uid>"; ls -ld /run/user/$(id -u); findmnt -no FSTYPE,OPTIONS /run/user/$(id -u)
echo; echo "## systemctl --user, inherited env"
systemctl --user is-system-running; echo "rc=$?"
echo; echo "## systemctl --user with XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS removed"
env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS systemctl --user is-system-running; echo "rc=$?"
echo; echo "## env -i (cron-like) systemctl --user"
env -i PATH=/usr/bin:/bin HOME="$HOME" systemctl --user is-system-running; echo "rc=$?"
echo; echo "## env -i systemctl --user --machine=$(id -un)@.host"
env -i PATH=/usr/bin:/bin HOME="$HOME" systemctl --user --machine="$(id -un)@.host" is-system-running; echo "rc=$?"
echo; echo "## env -i with XDG_RUNTIME_DIR=/run/user/\$uid only"
env -i PATH=/usr/bin:/bin HOME="$HOME" XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user is-system-running; echo "rc=$?"
echo; echo "## user manager environment (names; XDG_*/DBUS values)"
systemctl --user show-environment | sed -E '/^(XDG_|DBUS_)/!s/=.*$/=<value omitted>/'
echo; echo "## loginctl"
loginctl list-users
loginctl show-user "$(id -un)" -p Name -p UID -p Linger -p State -p RuntimePath -p Service -p Slice
echo "linger dir: $(ls -A /var/lib/systemd/linger 2>&1 | tr '\n' ' ')"
echo "logind KillUserProcesses: $(grep -h '^#\?KillUserProcesses' /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null | tr '\n' ' ')"
echo "~/.config/systemd/user exists: $([ -d ~/.config/systemd/user ] && echo yes || echo no)"

echo; echo "## ONE transient unit: Restart=always, RestartSec=500ms, body = print XDG, sleep 1, exit 1"
U="shp-lpg-probe-$(date +%s)"
systemd-run --user --unit="$U" -p Restart=always -p RestartSec=500ms --description="shepherd schema probe (throwaway)" \
  /bin/sh -c 'echo "start pid=$$ XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR-<unset>} XDG_DATA_HOME=${XDG_DATA_HOME-<unset>} XDG_CONFIG_HOME=${XDG_CONFIG_HOME-<unset>} DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS-<unset>} INVOCATION_ID=${INVOCATION_ID:+<set>} HOME=$HOME PWD=$PWD"; echo "env names: $(env | cut -d= -f1 | sort | tr "\n" " ")"; sleep 1; echo "exiting 1"; exit 1'
echo "systemd-run rc=$?"
for i in $(seq 1 14); do
  printf 't+%02ds ' "$i"; systemctl --user show "$U" -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p ExecMainStatus | tr '\n' ' '; echo
  sleep 1
done
echo; echo "## systemctl --user status (after loop)"
systemctl --user status "$U" --no-pager -n 0 | sed -n '1,6p'
echo; echo "## unit properties of interest"
systemctl --user show "$U" -p Restart -p RestartUSec -p StartLimitBurst -p StartLimitIntervalUSec -p StartLimitAction -p FragmentPath -p Transient -p ControlGroup
echo; echo "## journalctl --user -u $U"
journalctl --user -u "$U" --no-pager -o short-iso 2>&1 | head -60
echo; echo "## journalctl _SYSTEMD_USER_UNIT=$U (system journal view)"
journalctl _SYSTEMD_USER_UNIT="$U" --no-pager -o short-iso 2>&1 | head -30
echo; echo "## journal storage"; ls -d /var/log/journal /run/log/journal 2>&1; journalctl --user --disk-usage 2>&1
echo; echo "## teardown"
systemctl --user stop "$U" 2>&1; echo "stop rc=$?"
systemctl --user reset-failed "$U" 2>&1; echo "reset-failed rc=$?"
systemctl --user show "$U" -p LoadState -p ActiveState 2>&1
echo "done: $(date -u +%FT%TZ)"
