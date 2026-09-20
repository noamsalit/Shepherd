#!/usr/bin/env python3
"""Headless (-p) counterpart of probe_tui.py's scenarios, same capture hooks, for a TUI/headless
hook-parity comparison (2026-09-14). No tmux is used here.

Re-run:  python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_headless_parity.py
Output:  docs/probes/2026-09-14-schemas/tmux-tui/headless-<UTC stamp>/
Hooks/settings only in a mktemp dir under /tmp; cc10x disabled there; every run has a timeout.
"""
import datetime, json, os, subprocess, sys, tempfile

MODEL = "claude-haiku-4-5-20251001"
HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN = os.path.join(HERE, f"headless-{STAMP}")
os.makedirs(RUN)
ENV = {"HOME": "/root", "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}


def run(name, args, cwd):
    cmd = ["claude", "--model", MODEL, "--output-format", "json"] + args
    try:
        r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = "timeout", str(e.stdout), str(e.stderr)
    open(os.path.join(RUN, f"{name}.cmd.txt"), "w").write(" ".join(cmd) + f"\nrc={rc}\n")
    open(os.path.join(RUN, f"{name}.stdout.json"), "w").write(out or "")
    open(os.path.join(RUN, f"{name}.stderr.txt"), "w").write(err or "")
    try:
        return json.loads(out).get("session_id")
    except Exception:
        return None


def main():
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    open(os.path.join(RUN, "versions.txt"), "w").write(f"claude --version: {ver}\n")
    d = tempfile.mkdtemp(prefix="shp-hl-", dir="/tmp")
    H = os.path.join(RUN, "hooks-h.jsonl")
    sp = os.path.join(d, ".claude", "settings.json")
    subprocess.run([sys.executable, os.path.join(HERE, "make_settings.py"), sp, H, ver], check=True)
    s = json.load(open(sp)); s["remoteControlAtStartup"] = False; json.dump(s, open(sp, "w"), indent=1)
    open(os.path.join(RUN, "tmpdir.txt"), "w").write(d + "\n")
    marks = []

    def mark(n):
        marks.append((n, sum(1 for _ in open(H)) if os.path.exists(H) else 0))

    mark("h1_pong")
    sid = run("h1_pong", ["-p", "Reply with only the word PONG"], d)
    mark("h2_permission_default_mode")
    run("h2_permission_default_mode", ["--resume", sid, "-p", "Use the Bash tool to run exactly this command: touch perm-probe.txt"], d)
    mark("h3_compact")
    run("h3_compact", ["--resume", sid, "-p", "/compact"], d)
    mark("h4_rename")
    run("h4_rename", ["--resume", sid, "-p", "/rename shp-headless-title"], d)
    mark("h5_fork")
    run("h5_fork", ["--resume", sid, "--fork-session", "-p", "Reply with only the word FORKED"], d)
    mark("end")
    hs = [json.loads(l) for l in open(H)] if os.path.exists(H) else []
    out = []
    for (n, a), (_, b) in zip(marks, marks[1:]):
        out.append(f"== {n}")
        for h in hs[a:b]:
            p = h["payload"]
            extra = p.get("source") or p.get("reason") or p.get("notification_type") or p.get("trigger") or p.get("tool_name") or ""
            out.append(f"  {h['_captured_at']} {p.get('session_id','')[:8]} {h['_event']} {extra} {'session_title=' + p['session_title'] if 'session_title' in p else ''}")
    open(os.path.join(RUN, "event-sequence.txt"), "w").write(f"# {ver}\n" + "\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
