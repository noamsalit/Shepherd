#!/usr/bin/env bash
# Shepherd linux-process-git probe: credential store availability (Secret Service / keyring) and the
# language runtimes the spec's stack needs (Python 3.12 + sqlite, venv/pip, node/npm/tsc) (2026-09-14).
#
# Re-run: bash docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh
#
# Safety: installs nothing. A store/lookup/clear round trip is attempted ONLY if secret-tool exists
# AND org.freedesktop.secrets is reachable, and only with a throwaway attribute (service=shepherd-probe-<rand>).
# The mode-0600 file fallback (§13) is exercised inside a mktemp -d dir, never under ~/.config.
set -u
E="$(cd "$(dirname "$0")" && pwd)"; C="$E/captures"; mkdir -p "$C"
O="$C/secrets-runtime.txt"
exec > "$O" 2>&1
echo "claude_version: $(claude --version)"; echo "date_utc: $(date -u +%FT%TZ)"
. /etc/os-release; echo "os: $PRETTY_NAME"; echo "uname: $(uname -srm)"
chk() { printf '%-28s ' "$1"; if command -v "$1" >/dev/null 2>&1; then echo "$(command -v "$1")"; else echo "<not found>"; fi; }

echo; echo "######## Secret Service / keyring"
for b in secret-tool gnome-keyring-daemon kwalletd5 kwalletd6 kwallet-query pass keyctl dbus-daemon dbus-send busctl gdbus; do chk "$b"; done
echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS-<unset>}"
ls -l "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus" 2>&1
echo "\$ busctl --user status (session bus reachable?)"; timeout 10 busctl --user --no-pager status 2>&1 | head -5; echo "[rc=${PIPESTATUS[0]}]"
echo "\$ busctl --user list | grep -i -E 'secret|keyring|kwallet'"
timeout 10 busctl --user --no-pager list 2>&1 | grep -i -E 'secret|keyring|kwallet' || echo "<no secret/keyring/kwallet names on the session bus, including activatable>"
echo "\$ busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.DBus.Peer Ping"
timeout 10 busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.DBus.Peer Ping 2>&1; echo "[rc=$?]"
echo "\$ ls /usr/share/dbus-1/services | grep -i secret"; ls /usr/share/dbus-1/services 2>/dev/null | grep -i -E 'secret|keyring|kwallet' || echo "<none>"
echo "\$ dpkg -l (keyring related)"; dpkg -l 2>/dev/null | awk '$1=="ii"{print $2, $3}' | grep -i -E '^(libsecret|gnome-keyring|kwallet|libsecret-tools|python3-secretstorage|python3-keyring|pass) ' || echo "<no keyring packages installed>"
echo "\$ python3 -c 'import secretstorage'"; python3 -c 'import secretstorage' 2>&1; echo "[rc=$?]"
echo "\$ python3 -c 'import keyring'"; python3 -c 'import keyring' 2>&1; echo "[rc=$?]"
if command -v secret-tool >/dev/null 2>&1 && timeout 10 busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.DBus.Peer Ping >/dev/null 2>&1; then
  A="shepherd-probe-$RANDOM"
  echo "throwaway-value" | timeout 20 secret-tool store --label="shepherd probe" service "$A" account probe; echo "store rc=$?"
  timeout 20 secret-tool lookup service "$A" account probe; echo "lookup rc=$?"
  timeout 20 secret-tool clear service "$A" account probe; echo "clear rc=$?"
else
  echo "store/lookup round trip: SKIPPED (secret-tool absent or no org.freedesktop.secrets on the session bus)"
fi
echo "\$ kernel keyring (keyctl) present?"; chk keyctl; grep -E '^(key|keys)' /proc/keys 2>/dev/null | head -0; ls -l /proc/keys 2>&1

echo; echo "######## §13 fallback: mode-0600 file under a config dir (in a throwaway dir)"
T="$(mktemp -d /tmp/shp-lpg-cred.XXXXXX)"; mkdir -m 700 "$T/shepherd"
( umask 077; printf '{"credential_ref":"probe"}\n' > "$T/shepherd/credentials.json" )
stat -c '%A %a %U:%G %n' "$T/shepherd" "$T/shepherd/credentials.json" | sed "s#$T#<tmpdir>#"
echo "nobody read: $(runuser -u nobody -- cat "$T/shepherd/credentials.json" 2>&1 | sed "s#$T#<tmpdir>#")"
rm -rf "$T"

echo; echo "######## Python"
chk python3; python3 --version; ls -l "$(command -v python3)"
for v in 3.11 3.12 3.13; do chk python$v; done
python3 - <<'PY'
import sqlite3, sys, tempfile, os
print("sys.version:", sys.version.replace("\n", " "))
print("sqlite3.sqlite_version:", sqlite3.sqlite_version)
db = os.path.join(tempfile.mkdtemp(prefix="shp-lpg-sqlite."), "t.db")
c = sqlite3.connect(db)
def q(label, sql):
    try:
        print(f"{label}:", c.execute(sql).fetchall())
    except Exception as e:
        print(f"{label}: ERROR {type(e).__name__}: {e}")
q("journal_mode=WAL", "PRAGMA journal_mode=WAL")
q("json1 json_extract", "SELECT json_extract('{\"a\":[1,2]}', '$.a[1]')")
q("jsonb (3.45+)", "SELECT typeof(jsonb('{}'))")
q("CHECK enum", "CREATE TABLE s (state TEXT NOT NULL CHECK (state IN ('starting','running')))")
q("STRICT table (3.37+)", "CREATE TABLE t2 (a TEXT) STRICT")
q("RETURNING (3.35+)", "INSERT INTO s(state) VALUES ('running') RETURNING rowid, state")
q("conditional UPDATE rowcount path", "UPDATE s SET state='starting' WHERE state='running' RETURNING rowid")
q("compile_options (FTS5/JSON)", "SELECT compile_options FROM pragma_compile_options WHERE compile_options LIKE '%FTS5%' OR compile_options LIKE '%JSON%' OR compile_options LIKE 'THREADSAFE%'")
PY
echo "\$ sqlite3 (CLI)"; chk sqlite3
echo "\$ python3 -m pip --version"; python3 -m pip --version 2>&1; echo "[rc=$?]"
echo "\$ python3 -m ensurepip --version"; python3 -m ensurepip --version 2>&1 | tail -1; echo "[rc=${PIPESTATUS[0]}]"
V="$(mktemp -d /tmp/shp-lpg-venv.XXXXXX)"
echo "\$ python3 -m venv <tmp>/with-pip"; python3 -m venv "$V/with-pip" 2>&1 | sed "s#$V#<tmp>#g" | head -8; echo "[rc=${PIPESTATUS[0]}]"
echo "\$ python3 -m venv --without-pip <tmp>/nopip"; python3 -m venv --without-pip "$V/nopip" 2>&1 | sed "s#$V#<tmp>#g"; echo "[rc=${PIPESTATUS[0]}]"
ls "$V/nopip/bin" 2>&1 | tr '\n' ' '; echo
rm -rf "$V"
for b in pipx uv virtualenv mypy; do chk "$b"; done
echo "\$ dpkg -l python3-venv python3-pip python3.12-venv"; dpkg -l python3-venv python3-pip python3.12-venv 2>&1 | awk 'NR>5 || /no packages/'

echo; echo "######## Node / TypeScript"
for b in node nodejs npm npx tsc corepack bun deno; do chk "$b"; done
echo "login shell view: $(bash -lc 'command -v node npm tsc 2>/dev/null | tr "\n" " "' 2>/dev/null)<end>"
ls -d ~/.nvm ~/.volta ~/.fnm /usr/local/lib/node_modules 2>&1 | sed 's/^/  /'
echo "\$ claude binary type"; head -c 4 "$(readlink -f "$(command -v claude)")" | od -c | head -1; echo "size: $(stat -Lc %s "$(command -v claude)")"
echo "\$ tmux -V"; tmux -V
echo "\$ git --version"; git --version
echo "done: $(date -u +%FT%TZ)"
