#!/usr/bin/env python3
"""Shepherd linux-process-git probe: hook capture command (2026-09-14).

Usage as a hook command:  hook_capture.py <EventName> <log.jsonl> [<uds path>]

Appends ONE JSONL line to <log.jsonl>:
  {"_event", "_captured_at", "_claude_version", "_hook_pid", "_claude_pid",
   "_ancestry": [{pid, ppid, comm[, cmdline, exe]}...],   # cmdline/exe only up to the FIRST claude
   "_env_names": [...], "_env_selected": {...whitelisted, non-secret values...},
   "payload": <raw stdin bytes inserted verbatim>}
Then, like the spec's hookd.py, it writes the raw payload to <uds path> with a 250 ms
budget (waiting for a 1-byte ack so the listener can read SO_PEERCRED + /proc while
this process is still alive) and always exits 0.
"""
import os, sys, time, socket

SAFE_ENV = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR", "PWD", "SHLVL",
            "XDG_RUNTIME_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "TMUX_PANE", "SHP_CLAUDE_VERSION"}


def status(pid):
    name = ppid = None
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("Name:"):
                name = line.split("\t", 1)[1].strip()
            elif line.startswith("PPid:"):
                ppid = int(line.split("\t", 1)[1])
                break
    return name, ppid


def main():
    ev = sys.argv[1]
    log = sys.argv[2]
    sock = sys.argv[3] if len(sys.argv) > 3 else None
    raw = sys.stdin.buffer.read()
    now = time.time()
    chain, claude_pid, pid = [], None, os.getpid()
    while pid and pid > 1 and len(chain) < 20:
        try:
            name, ppid = status(pid)
        except OSError:
            break
        ent = {"pid": pid, "ppid": ppid, "comm": name}
        if claude_pid is None:
            try:
                ent["cmdline"] = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[:-1]
                ent["cmdline"] = [a.decode(errors="replace") for a in ent["cmdline"]]
                ent["exe"] = os.readlink(f"/proc/{pid}/exe")
            except OSError as e:
                ent["error"] = str(e)
        chain.append(ent)
        if name == "claude" and claude_pid is None:
            claude_pid = pid
        pid = ppid
    import json
    body = raw.rstrip(b"\n")
    try:
        pl = json.loads(body)
    except Exception:
        pl = {}
    env_pid = os.environ.get("CLAUDE_PID")
    env_sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    # booleans only: when these do NOT match they carry the id of whatever launched claude
    link = {
        "CLAUDE_PID_present": env_pid is not None,
        "CLAUDE_PID_equals_owning_claude_pid": env_pid is not None and env_pid == str(claude_pid),
        "CLAUDE_CODE_SESSION_ID_present": env_sid is not None,
        "CLAUDE_CODE_SESSION_ID_equals_payload_session_id": env_sid is not None and env_sid == pl.get("session_id"),
        "CLAUDE_PROJECT_DIR_equals_payload_cwd": os.environ.get("CLAUDE_PROJECT_DIR") == pl.get("cwd"),
        "PWD_equals_payload_cwd": os.environ.get("PWD") == pl.get("cwd"),
    }
    head = {
        "_event": ev,
        "_captured_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + ".%03dZ" % int((now % 1) * 1000),
        "_claude_version": os.environ.get("SHP_CLAUDE_VERSION", "unknown"),
        "_hook_pid": os.getpid(),
        "_claude_pid": claude_pid,
        "_ancestry": chain,
        "_env_names": sorted(os.environ),
        "_env_selected": {k: os.environ[k] for k in sorted(SAFE_ENV) if k in os.environ},
        "_env_link": link,
    }
    line = json.dumps(head)[:-1].encode() + b', "payload": ' + (body if body else b"null") + b"}\n"
    with open(log, "ab") as f:
        f.write(line)
    if sock:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.25)
        s.connect(sock)
        s.sendall(body)
        s.shutdown(socket.SHUT_WR)
        s.recv(1)
        s.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
