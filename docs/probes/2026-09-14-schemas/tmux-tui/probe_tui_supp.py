#!/usr/bin/env python3
"""Shepherd schema probe, supplement to probe_tui.py (2026-09-14).

Covers: --name / --session-id at spawn (title and id visible before the first turn),
capture-pane -S -2000 scrollback while the TUI is on the alternate screen,
pipe-pane live byte stream.

Re-run:  python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp.py
Output:  docs/probes/2026-09-14-schemas/tmux-tui/supp-<UTC stamp>/
Same safety rules as probe_tui.py: -L shepherd-probe on every tmux call, "=<name>:" targets,
no ':' in names, teardown only via "tmux -L shepherd-probe kill-server".
"""
import datetime, json, os, subprocess, sys, tempfile, time, uuid

SOCK = "shepherd-probe"
MODEL = "claude-haiku-4-5-20251001"
HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
RUN = os.path.join(HERE, f"supp-{STAMP}")
os.makedirs(RUN)
CLEAN_ENV = ["env", "-i", "HOME=/root", "PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
             "TERM=xterm-256color", "LANG=C.UTF-8"]


def log(m):
    line = f"{datetime.datetime.utcnow().isoformat(timespec='milliseconds')}Z {m}"
    print(line, flush=True)
    open(os.path.join(RUN, "steps.log"), "a").write(line + "\n")


def tm(*args, env_clean=False):
    return subprocess.run((CLEAN_ENV if env_clean else []) + ["tmux", "-L", SOCK] + list(args),
                          capture_output=True, text=True)


def save(name, text):
    p = os.path.join(RUN, name); open(p, "w").write(text); return p


def hooks(p):
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def wait(p, pred, timeout, after=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for h in hooks(p)[after:]:
            if pred(h):
                return h
        time.sleep(0.5)
    return None


def main():
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    save("versions.txt", f"claude --version: {ver}\ntmux -V: {subprocess.run(['tmux','-V'],capture_output=True,text=True).stdout.strip()}\n")
    if tm("ls").returncode == 0:
        log("probe socket busy; refusing"); sys.exit(2)
    d = tempfile.mkdtemp(prefix="shp-tui-S-", dir="/tmp")
    H = os.path.join(RUN, "hooks-s.jsonl")
    sp = os.path.join(d, ".claude", "settings.json")
    subprocess.run([sys.executable, os.path.join(HERE, "make_settings.py"), sp, H, ver], check=True)
    s = json.load(open(sp)); s["remoteControlAtStartup"] = False; json.dump(s, open(sp, "w"), indent=1)
    sid = str(uuid.uuid4())
    save("tmpdir-and-ids.txt", f"dir={d}\nrequested --session-id={sid}\n")
    try:
        cmd = f"claude --model {MODEL} --name shp-spawn-name --session-id {sid} --debug-file {RUN}/debug-s.log"
        tm("new-session", "-d", "-s", "probe_s", "-x", "120", "-y", "30", "-c", d, cmd, env_clean=True)
        tm("set-option", "-w", "-t", "=probe_s:", "remain-on-exit", "on")
        save("spawn-cmd.txt", cmd + "\n")
        time.sleep(6)
        save("01-trust.txt", tm("capture-pane", "-p", "-t", "=probe_s:").stdout)
        tm("send-keys", "-t", "=probe_s:", "Down"); time.sleep(1)
        tm("send-keys", "-t", "=probe_s:", "Enter")
        h = wait(H, lambda h: h["_event"] == "SessionStart", 40)
        time.sleep(3)
        pid = tm("display-message", "-p", "-t", "=probe_s:", "#{pane_pid}").stdout.strip()
        sc = f"/root/.claude/sessions/{pid}.json"
        save("02-sessionstart-and-sidecar.txt",
             f"SessionStart.session_id == requested: {h and h['payload'].get('session_id') == sid}\n"
             f"pane_title={tm('display-message','-p','-t','=probe_s:','#{pane_title}').stdout.strip()}\n"
             f"transcript exists before first prompt: {os.path.exists(h['payload']['transcript_path']) if h else None}\n"
             f"sidecar: {open(sc).read() if os.path.exists(sc) else '<absent>'}\n")
        # live byte stream
        pty = os.path.join(RUN, "03-pipe-pane.raw")
        tm("pipe-pane", "-o", "-t", "=probe_s:", f"cat >> {pty}")
        n0 = len(hooks(H))
        tm("send-keys", "-t", "=probe_s:", "-l", "Print the integers from 1 to 80, one per line, nothing else.")
        tm("send-keys", "-t", "=probe_s:", "Enter")
        wait(H, lambda h: h["_event"] == "Stop", 90, after=n0)
        time.sleep(3)
        tm("pipe-pane", "-t", "=probe_s:")  # stop piping
        f = "#{alternate_on} #{history_size} #{history_limit} #{pane_height}"
        vals = tm("display-message", "-p", "-t", "=probe_s:", f).stdout.strip()
        full = tm("capture-pane", "-p", "-S", "-2000", "-t", "=probe_s:").stdout
        vis = tm("capture-pane", "-p", "-t", "=probe_s:").stdout
        save("04-capture-S2000.txt", full)
        save("04-capture-visible.txt", vis)
        ansi = tm("capture-pane", "-e", "-p", "-S", "-2000", "-t", "=probe_s:").stdout
        save("04-capture-e-S2000.ansi", ansi)
        save("04-capture-e-S2000.ansi.cat-v.txt", subprocess.run(["cat", "-v"], input=ansi.encode(), capture_output=True).stdout.decode())
        lines = [l.strip() for l in full.splitlines()]
        save("04-scrollback-stats.txt",
             f"format '{f}' -> {vals}\n"
             f"capture -S -2000 lines={len(full.splitlines())} visible lines={len(vis.splitlines())}\n"
             f"'1' present in -S -2000 capture: {'1' in lines}; '80' present: {'80' in lines}\n"
             f"ESC count in -e capture: {ansi.count(chr(27))}\n"
             f"pipe-pane raw bytes: {os.path.getsize(pty) if os.path.exists(pty) else 0}\n")
        raw = open(pty, "rb").read() if os.path.exists(pty) else b""
        save("03-pipe-pane-head.cat-v.txt", subprocess.run(["cat", "-v"], input=raw[:1500], capture_output=True).stdout.decode())
        save("05-hook-sequence.txt", "\n".join(f"{x['_captured_at']} {x['_event']} {json.dumps({k: x['payload'].get(k) for k in ('source','session_title','reason','notification_type') if k in x['payload']})}" for x in hooks(H)) + "\n")
    finally:
        tm("kill-server")
        r = tm("ls")
        save("teardown.txt", f"after kill-server: rc={r.returncode} err={r.stderr.strip()}\n")


if __name__ == "__main__":
    main()
