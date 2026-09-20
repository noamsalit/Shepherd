#!/usr/bin/env python3
"""Interactive (TUI) hook probe driven through a private pty (python pty.fork, NOT tmux)
for the events -p cannot reach: Notification(permission_prompt, idle_prompt),
SessionEnd(clear / prompt_input_exit), SessionStart(clear), DirectoryAdded (2026-09-14).

Re-run: python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py
Output: live/I01_interactive/{events.jsonl, settings.json, meta.json, steps.txt, screen-tail.txt}
Safety: throwaway cwd under /tmp, hooks only in <tmpdir>/.claude/settings.json, cc10x disabled,
CLAUDE* env scrubbed, haiku model, hard deadline; only the child we forked is ever signalled.
"""
import json, os, pty, re, select, signal, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_probes as rp  # noqa: E402

NAME = "I01_interactive"
OUT = os.path.join(rp.LIVE, NAME)
os.makedirs(OUT, exist_ok=True)
for f in ("events.jsonl", "steps.txt"):
    if os.path.exists(os.path.join(OUT, f)):
        os.remove(os.path.join(OUT, f))
d = rp.mktmp("tui")
extra_dir = rp.mktmp("tui-extra")
victim = rp.mktmp("tui-victim")
settings = rp.build_settings(OUT)
os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
json.dump(settings, open(os.path.join(d, ".claude", "settings.json"), "w"), indent=1)
json.dump(settings, open(os.path.join(OUT, "settings.json"), "w"), indent=1)
steps = open(os.path.join(OUT, "steps.txt"), "a")
screen = bytearray()
ANSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][A-Z0-9]|\x1b[=>]")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line); steps.write(line + "\n"); steps.flush()


def events():
    p = os.path.join(OUT, "events.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p):
        try:
            r = json.loads(l); out.append((r["_event"], r["payload"]))
        except Exception:
            pass
    return out


pid, fd = pty.fork()
if pid == 0:
    os.chdir(d)
    env = rp.child_env({"TERM": "xterm-256color", "COLUMNS": "120", "LINES": "40"})
    env.pop("TMUX", None)
    os.execvpe("claude", ["claude", "--model", rp.HAIKU, "--debug-file", os.path.join(d, ".debug-I01.log")], env)

import fcntl, struct, termios  # noqa: E402
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
DEADLINE = time.time() + 460


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end and time.time() < DEADLINE:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                data = os.read(fd, 65536)
            except OSError:
                return False
            if not data:
                return False
            screen.extend(data)
            del screen[:-200000]
    return True


def text():
    return ANSI.sub(b"", bytes(screen[-20000:])).decode("utf8", "replace")


def send(s, label):
    log(f"send {label!r}")
    os.write(fd, s.encode())


def wait_for(pred, seconds, label):
    end = time.time() + seconds
    while time.time() < end:
        if not pump(0.5):
            log(f"pty closed while waiting for {label}")
            return False
        if pred():
            log(f"ok: {label}")
            return True
    log(f"TIMEOUT waiting for {label}")
    return False


def has_event(name, **kw):
    return lambda: any(e == name and all(p.get(k) == v for k, v in kw.items()) for e, p in events())


t0 = time.time()
try:
    pump(6)
    if re.search(r"trust|Trust", text()):
        log("trust dialog seen -> Down + Enter ('Yes, I trust this folder')")
        send("\x1b[B", "down"); pump(1)
        send("\r", "enter")
        pump(4)
    wait_for(has_event("SessionStart"), 40, "SessionStart")
    pump(3)
    send(f"Use the Write tool to create the file {victim}/outside.txt containing the text x", "prompt needing permission"); pump(1.5); send("\r", "enter")
    wait_for(has_event("PermissionRequest"), 60, "PermissionRequest")
    wait_for(has_event("Notification", notification_type="permission_prompt"), 30, "Notification permission_prompt")
    pump(2)
    send("\x1b", "Esc (reject permission)")
    wait_for(has_event("Stop"), 20, "Stop after reject (observed: none fires)")
    pump(2)
    send("Reply with the single word OK", "plain prompt"); pump(1.5); send("\r", "enter")
    wait_for(has_event("Stop"), 60, "Stop after plain prompt")
    log("no keystrokes now; idling for idle_prompt notification (up to 100s)")
    wait_for(has_event("Notification", notification_type="idle_prompt"), 100, "Notification idle_prompt")
    send(f"/add-dir {extra_dir}", "add-dir text"); pump(1.5); send("\r", "enter")
    pump(4)
    if re.search(r"(Yes|remember|session)", text()[-3000:]):
        send("\r", "enter (confirm add-dir dialog)")
    wait_for(has_event("DirectoryAdded"), 20, "DirectoryAdded")
    pump(2)
    send("/clear", "clear text"); pump(1.5); send("\r", "enter")
    wait_for(has_event("SessionStart", source="clear"), 30, "SessionStart clear")
    pump(3)
    send("/exit", "exit text"); pump(1.5); send("\r", "enter")
    wait_for(lambda: has_event("SessionEnd", reason="prompt_input_exit")(), 30, "SessionEnd prompt_input_exit")
    pump(5)
finally:
    try:
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid == 0:
            log("child still alive at end -> SIGTERM (our own forked child)")
            os.kill(pid, signal.SIGTERM)
            time.sleep(3)
            wpid, status = os.waitpid(pid, os.WNOHANG)
            if wpid == 0:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    open(os.path.join(OUT, "screen-tail.txt"), "w").write(text()[-4000:])
    json.dump({"scenario": NAME, "claude_version": rp.VERSION, "cwd": d, "extra_dir": extra_dir, "victim_dir": victim,
               "victim_outside_exists": os.path.exists(os.path.join(victim, "outside.txt")),
               "duration_s": round(time.time() - t0, 1), "events": [e for e, _ in events()],
               "driver": "python pty.fork (no tmux)", "user_settings_sha256": rp.sha(rp.USER_SETTINGS)},
              open(os.path.join(OUT, "meta.json"), "w"), indent=1)
    dbg = os.path.join(d, ".debug-I01.log")
    if os.path.exists(dbg):
        open(os.path.join(OUT, "debug-hooklines.txt"), "w").writelines(
            l for l in open(dbg, errors="replace") if re.search(r"hook|Hook|Notification|notif", l))
    log("done: " + str([e for e, _ in events()]))
