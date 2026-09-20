#!/usr/bin/env python3
"""Shepherd linux-process-git probe: read-only /proc snapshot of every claude process (2026-09-14).

Usage: proc_snapshot.py <out.json> <own-marker> [<own-marker> ...]

A process is "own" (a throwaway session this probe started) when any marker string occurs in
its cmdline or its cwd. Own processes are captured raw (stat line, argv, cwd, exe, env NAMES,
status, cgroup, fd summary). Every other claude process (the user's live sessions) is reduced
to a shape: comm, exe basename, flag names from argv with values replaced by <redacted>,
env var names only, parent comm, cgroup. No env values, no argv values, no cwd of others.
"""
import json, os, re, sys

out, markers = sys.argv[1], sys.argv[2:]
STAT_NAMES = {1: "pid", 2: "comm", 3: "state", 4: "ppid", 5: "pgrp", 6: "session", 7: "tty_nr",
              8: "tpgid", 9: "flags", 14: "utime", 15: "stime", 19: "nice", 20: "num_threads",
              22: "starttime", 23: "vsize", 24: "rss"}


def rd(p, mode="r"):
    with open(p, mode) as f:
        return f.read()


def parse_stat(s):
    lp, rp = s.index("("), s.rindex(")")
    fields = [s[:lp].strip(), s[lp + 1:rp]] + s[rp + 2:].split()
    return fields


def comm_of(pid):
    try:
        return rd(f"/proc/{pid}/comm").strip()
    except OSError:
        return None


res = {"clk_tck": os.sysconf("SC_CLK_TCK"),
       "btime": int([l for l in open("/proc/stat") if l.startswith("btime")][0].split()[1]),
       "own": [], "others": []}
for d in sorted(os.listdir("/proc"), key=lambda x: (not x.isdigit(), x)):
    if not d.isdigit():
        continue
    pid = int(d)
    try:
        comm = rd(f"/proc/{pid}/comm").strip()
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        continue
    if comm != "claude" and "/claude/versions/" not in exe:
        continue
    try:
        argv = [a.decode(errors="replace") for a in rd(f"/proc/{pid}/cmdline", "rb").split(b"\0")[:-1]]
        cwd = os.readlink(f"/proc/{pid}/cwd")
        env = rd(f"/proc/{pid}/environ", "rb").split(b"\0")
        env_names = sorted({e.split(b"=", 1)[0].decode(errors="replace") for e in env if e})
        envd = dict(e.decode(errors="replace").split("=", 1) for e in env if b"=" in e)
        stat = rd(f"/proc/{pid}/stat").rstrip("\n")
        status = {l.split(":", 1)[0]: l.split(":", 1)[1].strip() for l in rd(f"/proc/{pid}/status").splitlines()
                  if l.split(":", 1)[0] in ("Name", "State", "Tgid", "PPid", "Uid", "Threads")}
        cgroup = rd(f"/proc/{pid}/cgroup").strip()
    except OSError as e:
        res["others"].append({"pid": "<redacted>", "error": repr(e)})
        continue
    f = parse_stat(stat)
    own = any(m in " ".join(argv) or cwd.startswith(m) for m in markers)
    ppid = int(f[3])
    if own:
        fds = {}
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                t = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            k = re.sub(r"\[\d+\]", "[N]", t) if ":" in t.split("/")[0] else t
            fds[k] = fds.get(k, 0) + 1
        res["own"].append({
            "stat_raw": stat,
            "stat_field_count": len(f),
            "stat_named_fields": {f"{i}:{n}": f[i - 1] for i, n in STAT_NAMES.items()},
            "starttime_epoch_s": res["btime"] + int(f[21]) / res["clk_tck"],
            "comm": comm, "exe": exe, "argv": argv, "cwd": cwd,
            "env_names": env_names, "status": status, "cgroup": cgroup,
            "parent": {"pid": ppid, "comm": comm_of(ppid)},
            "fd_targets": fds,
            # booleans only: values that do not match belong to whatever launched this claude
            "environ_link": {
                "CLAUDE_PID_present": "CLAUDE_PID" in envd,
                "CLAUDE_PID_equals_this_pid": envd.get("CLAUDE_PID") == str(pid),
                "CLAUDE_CODE_SESSION_ID_present": "CLAUDE_CODE_SESSION_ID" in envd,
                "CLAUDE_CODE_SESSION_ID_equals_a_marker_of_this_session": envd.get("CLAUDE_CODE_SESSION_ID") in markers,
                "PWD_equals_proc_cwd": envd.get("PWD") == cwd,
            },
            "threads_comm_counts": {},
        })
        for t in os.listdir(f"/proc/{pid}/task"):
            try:
                n = rd(f"/proc/{pid}/task/{t}/comm").strip()
            except OSError:
                continue
            res["own"][-1]["threads_comm_counts"][n] = res["own"][-1]["threads_comm_counts"].get(n, 0) + 1
    else:
        flags = [a if a.startswith("-") else "<redacted>" for a in argv[1:]]
        res["others"].append({
            "pid": "<redacted>", "comm": comm, "exe_basename": os.path.basename(exe),
            "exe_dir_pattern": re.sub(r"[^/]+$", "<version>", exe),
            "argv0": argv[0] if argv else None, "argv_shape": flags,
            "cwd": "<redacted>", "cwd_is_absolute": cwd.startswith("/"),
            "env_name_count": len(env_names), "env_names": env_names,
            "stat_field_count": len(f), "status_Name": status.get("Name"),
            "parent_comm": comm_of(ppid), "cgroup": cgroup,
        })
json.dump(res, open(out, "w"), indent=1)
print(out)
