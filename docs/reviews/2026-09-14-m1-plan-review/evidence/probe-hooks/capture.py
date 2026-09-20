#!/usr/bin/env python3
import sys, json, os, datetime
LOG = os.environ.get("CAPTURE_LOG") or sys.argv[2]
try:
    raw = sys.stdin.buffer.read()
    rec = {"_captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "_argv_event": sys.argv[1] if len(sys.argv) > 1 else None,
           "_raw_len": len(raw), "_env_CLAUDE_EFFORT": os.environ.get("CLAUDE_EFFORT"),
           "_env_CLAUDE_PROJECT_DIR": os.environ.get("CLAUDE_PROJECT_DIR")}
    try:
        rec["payload"] = json.loads(raw)
    except Exception:
        rec["payload_unparsed"] = raw[:4000].decode("utf8", "replace")
    anc = []
    pid = os.getpid()
    for _ in range(10):
        try:
            st = open(f"/proc/{pid}/stat").read()
            comm = st[st.index("(")+1: st.rindex(")")]
            rest = st[st.rindex(")")+2:].split()
            ppid = int(rest[1])
            try:
                cmd = open(f"/proc/{pid}/cmdline","rb").read().replace(b"\0", b" ").decode("utf8","replace")[:200]
            except Exception:
                cmd = None
            try:
                exe = os.readlink(f"/proc/{pid}/exe")
            except Exception:
                exe = None
            anc.append({"pid": pid, "comm": comm, "ppid": ppid, "exe": exe, "cmdline": cmd})
            if ppid <= 1: break
            pid = ppid
        except Exception as e:
            anc.append({"error": repr(e)}); break
    rec["_ancestry"] = anc
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
except BaseException:
    pass
sys.exit(0)
