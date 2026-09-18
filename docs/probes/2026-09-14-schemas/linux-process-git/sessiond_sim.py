#!/usr/bin/env python3
"""Shepherd linux-process-git probe: a minimal stand-in for sessiond's hook-ingest UDS (2026-09-14).

Usage: sessiond_sim.py <socket path> <out.jsonl> <seconds to run>

Binds an AF_UNIX stream socket with umask 0177 (so it is created 0600, no chmod race),
parent dir must already be 0700. For every connection it records, BEFORE reading the body:
  SO_PEERCRED (pid, uid, gid) -> walk /proc PPid chain to the nearest process whose comm is
  "claude" -> that pid's /proc/<pid>/stat starttime (field 22) -> ~/.claude/sessions/<pid>.json
  (sessionId, procStart only) if it exists.
Then reads the payload, extracts session_id / hook_event_name, acks one byte.
"""
import json, os, socket, struct, sys, time

path, out, secs = sys.argv[1], sys.argv[2], float(sys.argv[3])
CLK = os.sysconf("SC_CLK_TCK")
BTIME = int([l for l in open("/proc/stat") if l.startswith("btime")][0].split()[1])


def stat_fields(pid):
    s = open(f"/proc/{pid}/stat").read()
    lp, rp = s.index("("), s.rindex(")")
    rest = s[rp + 2:].split()
    return {"pid": int(s[:lp]), "comm": s[lp + 1:rp], "state": rest[0], "ppid": int(rest[1]),
            "starttime": int(rest[19])}  # field 22 overall = index 19 after pid, comm


old = os.umask(0o177)
if os.path.exists(path):
    os.unlink(path)
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(path)
os.umask(old)
srv.listen(64)
srv.settimeout(1.0)
end = time.time() + secs
with open(out, "a") as f:
    f.write(json.dumps({"_listener": "started", "socket": path,
                        "socket_mode": oct(os.stat(path).st_mode & 0o777),
                        "dir_mode": oct(os.stat(os.path.dirname(path)).st_mode & 0o777),
                        "clk_tck": CLK, "btime": BTIME}) + "\n")
    while time.time() < end:
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        t0 = time.time()
        pid, uid, gid = struct.unpack("3i", c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        rec = {"peercred": {"pid": pid, "uid": uid, "gid": gid}, "walk": []}
        p, claude = pid, None
        try:
            while p > 1 and len(rec["walk"]) < 20:
                sf = stat_fields(p)
                rec["walk"].append({"pid": sf["pid"], "comm": sf["comm"], "ppid": sf["ppid"]})
                if sf["comm"] == "claude":
                    claude = sf
                    break
                p = sf["ppid"]
        except OSError as e:
            rec["walk_error"] = repr(e)
        if claude:
            rec["claude_pid"] = claude["pid"]
            rec["claude_stat_starttime"] = claude["starttime"]
            rec["claude_start_epoch_s"] = BTIME + claude["starttime"] / CLK
            reg = f"/root/.claude/sessions/{claude['pid']}.json"
            if os.path.exists(reg):
                r = json.load(open(reg))
                rec["registry"] = {k: r.get(k) for k in ("sessionId", "procStart", "startedAt", "pid")}
            else:
                rec["registry"] = None
        rec["walk_ms"] = round((time.time() - t0) * 1000, 2)
        c.settimeout(1.0)
        data = b""
        try:
            while True:
                b = c.recv(65536)
                if not b:
                    break
                data += b
            c.sendall(b"k")
        except OSError as e:
            rec["recv_error"] = repr(e)
        c.close()
        try:
            d = json.loads(data)
            rec["payload_session_id"] = d.get("session_id")
            rec["payload_event"] = d.get("hook_event_name")
        except Exception as e:
            rec["payload_parse_error"] = repr(e)
        rec["payload_bytes"] = len(data)
        f.write(json.dumps(rec) + "\n")
        f.flush()
srv.close()
os.unlink(path)
