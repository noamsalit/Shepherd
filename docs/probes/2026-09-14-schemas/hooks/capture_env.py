#!/usr/bin/env python3
"""Hook-runtime probe: record what a hook process receives (2026-09-14).

Usage (as a hook command): capture_env.py <EventName> <log.jsonl>
Records env var NAMES (all) and VALUES only for a non-secret allowlist
(values of any key containing TOKEN/KEY/SECRET/AUTH/PASSWORD/COOKIE are <redacted>),
plus stdin facts (isatty, bytes read, EOF), hook cwd, argv, and full ancestry
with cmdline of each ancestor. Always exits 0.
"""
import datetime, json, os, sys

SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "AUTH", "PASSWORD", "COOKIE", "CREDENTIAL")


def ancestry():
    out, pid = [], os.getpid()
    for _ in range(14):
        try:
            st = open(f"/proc/{pid}/stat").read()
            comm = st[st.index("(") + 1: st.rindex(")")]
            ppid = int(st[st.rindex(")") + 2:].split()[1])
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf8", "replace")[:300]
            except Exception:
                cmd = None
            try:
                exe = os.readlink(f"/proc/{pid}/exe")
            except Exception:
                exe = None
            out.append({"pid": pid, "comm": comm, "ppid": ppid, "exe": exe, "cmdline": cmd})
            if ppid <= 1:
                break
            pid = ppid
        except Exception as e:  # noqa: BLE001
            out.append({"error": repr(e)})
            break
    return out


def main() -> None:
    ev = sys.argv[1] if len(sys.argv) > 1 else None
    log = sys.argv[2]
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    tty = sys.stdin.isatty()
    raw = sys.stdin.buffer.read()
    env = {}
    for k in sorted(os.environ):
        v = os.environ[k]
        if any(m in k.upper() for m in SECRET_MARKERS):
            v = "<redacted>"
        elif not (k.startswith("CLAUDE") or k.startswith("SHP_") or k in (
                "PWD", "SHELL", "HOME", "PATH", "TERM", "USER", "LANG", "TMUX", "NODE_OPTIONS",
                "OLDPWD", "SHLVL", "_", "COLORTERM", "FORCE_COLOR", "NO_COLOR", "CI", "GIT_EDITOR",
                "COREPACK_ENABLE_AUTO_PIN", "DISABLE_AUTOUPDATER", "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE",
                "BUN_INSTALL", "NoDefaultCurrentDirectoryInExePath", "ENABLE_IDE_INTEGRATION")):
            v = "<not-recorded>"
        env[k] = v
    rec = {
        "_event": ev, "_captured_at": ts, "_claude_version": os.environ.get("SHP_CLAUDE_VERSION"),
        "_argv": sys.argv, "_hook_cwd": os.getcwd(), "_stdin_isatty": tty, "_stdin_bytes": len(raw),
        "_env": env, "_ancestry": ancestry(),
        "_fds": sorted(os.listdir("/proc/self/fd")),
    }
    with open(log, "a") as f:
        f.write(json.dumps(rec) + "\n")


try:
    main()
except BaseException:
    pass
sys.exit(0)
