#!/usr/bin/env python3
"""Throwaway hook logger for review probe. Appends raw stdin + event + timestamp + ancestry to JSONL. Always exits 0."""
import sys, os, json, datetime, subprocess
try:
    log = sys.argv[1]; label = sys.argv[2] if len(sys.argv) > 2 else ""
    raw = sys.stdin.read()
    rec = {"_t": datetime.datetime.now(datetime.timezone.utc).isoformat(), "_label": label, "_raw_len": len(raw), "_raw": raw}
    try:
        p = json.loads(raw); rec["hook_event_name"] = p.get("hook_event_name")
    except Exception as e:
        rec["parse_error"] = repr(e)
    anc = []; pid = os.getpid()
    for _ in range(12):
        try:
            with open(f"/proc/{pid}/stat") as f: st = f.read()
            comm = st[st.index("(")+1: st.rindex(")")]
            rest = st[st.rindex(")")+2:].split()
            ppid = int(rest[1])
            try: exe = os.readlink(f"/proc/{pid}/exe")
            except Exception: exe = None
            with open(f"/proc/{pid}/cmdline","rb") as f: cmd = f.read().replace(b"\0", b" ").decode(errors="replace")[:200]
            anc.append({"pid": pid, "comm": comm, "exe": exe, "cmdline": cmd})
            if ppid <= 1: break
            pid = ppid
        except Exception as e:
            anc.append({"error": repr(e)}); break
    rec["_ancestry"] = anc
    rec["_ps_chain"] = subprocess.run(["ps", "-o", "pid,ppid,comm,args", "-p", ",".join(str(a.get("pid")) for a in anc if "pid" in a)], capture_output=True, text=True, timeout=2).stdout
    with open(log, "a") as f: f.write(json.dumps(rec) + "\n")
except BaseException:
    pass
sys.exit(0)
