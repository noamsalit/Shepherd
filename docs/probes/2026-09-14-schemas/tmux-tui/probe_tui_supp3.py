#!/usr/bin/env python3
"""Shepherd schema probe, third supplement (2026-09-14): typing a message over prompt-suggestion ghost text.

When a prompt suggestion is shown in the input box after Stop, a mailbox delivery would
type over it with send-keys -l. Does the submitted prompt equal exactly what was typed?

Re-run:  python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui_supp3.py
Output:  docs/probes/2026-09-14-schemas/tmux-tui/supp3-<UTC stamp>/
Safety: -L shepherd-probe on every tmux call, "=<name>:" targets, teardown via
"tmux -L shepherd-probe kill-server" only, hooks/settings only in a mktemp dir.
"""
import datetime, json, os, re, subprocess, sys, tempfile, time

SOCK = "shepherd-probe"
MODEL = "claude-haiku-4-5-20251001"
HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN = os.path.join(HERE, f"supp3-{STAMP}")
os.makedirs(RUN)
CLEAN_ENV = ["env", "-i", "HOME=/root", "PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
             "TERM=xterm-256color", "LANG=C.UTF-8"]
T = "=probe_x:"


def log(m):
    line = f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')} {m}"
    print(line, flush=True); open(os.path.join(RUN, "steps.log"), "a").write(line + "\n")


def tm(*a, env_clean=False):
    return subprocess.run((CLEAN_ENV if env_clean else []) + ["tmux", "-L", SOCK] + list(a), capture_output=True, text=True)


def save(n, t):
    open(os.path.join(RUN, n), "w").write(t)


def cap(n, ansi=False):
    out = tm("capture-pane", "-p", *(["-e"] if ansi else []), "-t", T).stdout
    save(n, out)
    if ansi:
        save(n + ".cat-v.txt", subprocess.run(["cat", "-v"], input=out.encode(), capture_output=True).stdout.decode())
    return out


def hooks(p):
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def wait(p, name, timeout, after=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for h in hooks(p)[after:]:
            if h["_event"] == name:
                return h
        time.sleep(0.5)
    return None


def prompt_line(screen):
    # the input box is the "❯ " line between the last two horizontal rules
    rules = [i for i, l in enumerate(screen.splitlines()) if l.startswith("────")]
    if len(rules) < 2:
        return None
    for l in screen.splitlines()[rules[-2] + 1:rules[-1]]:
        if l.startswith("❯"):
            return l
    return None


def seq(p, after):
    return [[h["_captured_at"], h["_event"], h["payload"].get("prompt") or h["payload"].get("notification_type") or h["payload"].get("tool_name")] for h in hooks(p)[after:]]


def main():
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    save("versions.txt", f"claude --version: {ver}\n")
    if tm("ls").returncode == 0:
        log("probe socket busy"); sys.exit(2)
    d = tempfile.mkdtemp(prefix="shp-tui-X-", dir="/tmp")
    H = os.path.join(RUN, "hooks-x.jsonl")
    sp = os.path.join(d, ".claude", "settings.json")
    subprocess.run([sys.executable, os.path.join(HERE, "make_settings.py"), sp, H, ver], check=True)
    s = json.load(open(sp)); s["remoteControlAtStartup"] = False; json.dump(s, open(sp, "w"), indent=1)
    save("tmpdir.txt", d + "\n")
    try:
        tm("new-session", "-d", "-s", "probe_x", "-x", "140", "-y", "40", "-c", d, f"claude --model {MODEL}", env_clean=True)
        tm("set-option", "-w", "-t", T, "remain-on-exit", "on")
        time.sleep(6); tm("send-keys", "-t", T, "Down"); time.sleep(1); tm("send-keys", "-t", T, "Enter")
        wait(H, "SessionStart", 40); time.sleep(2)
        # ---- A: suggestion ghost text
        prompts = ["Use the Bash tool to run exactly this command: touch notes.txt",
                   "Use the Bash tool to run exactly: ls -la",
                   "Use the Bash tool to run exactly this command: echo hello > hello.txt",
                   "Reply with one short sentence describing the files in this directory."]
        found = False
        for k, ptxt in enumerate(prompts):
            n0 = len(hooks(H))
            tm("send-keys", "-t", T, "-l", ptxt); tm("send-keys", "-t", T, "Enter")
            t0 = time.time()
            while time.time() - t0 < 60:
                hs = hooks(H)[n0:]
                if any(h["_event"] == "PermissionRequest" for h in hs) and not any(h["_event"] in ("PostToolUse", "Stop") for h in hs):
                    time.sleep(1); tm("send-keys", "-t", T, "Enter"); time.sleep(3)  # approve (option 1 Yes)
                if any(h["_event"] == "Stop" for h in hs):
                    break
                time.sleep(0.5)
            wait(H, "SubagentStop", 20, after=n0)
            for _ in range(10):
                time.sleep(1)
                scr = tm("capture-pane", "-p", "-t", T).stdout
                pl = prompt_line(scr)
                if pl and pl.strip() not in ("❯",):
                    found = True; break
            if found:
                log(f"A: suggestion visible after prompt {k}: {pl!r}")
                cap("A1-suggestion.txt"); cap("A1-suggestion.ansi", ansi=True)
                n1 = len(hooks(H))
                tm("send-keys", "-t", T, "-l", "Reply with only the word GHOST")
                time.sleep(1)
                cap("A2-typed-over-suggestion.txt"); cap("A2-typed-over-suggestion.ansi", ansi=True)
                tm("send-keys", "-t", T, "Enter"); time.sleep(8)
                cap("A3-after-enter.txt")
                save("A3-hooks-after-enter.json", json.dumps(seq(H, n1), indent=1) + "\n")
                wait(H, "Stop", 40, after=n1); time.sleep(2)
                break
        save("A0-suggestion-found.txt", f"suggestion ghost text seen: {found} (after {k + 1} prompts)\n")
    finally:
        tm("kill-server")
        r = tm("ls"); save("teardown.txt", f"after kill-server: rc={r.returncode} err={r.stderr.strip()}\n")


if __name__ == "__main__":
    main()
