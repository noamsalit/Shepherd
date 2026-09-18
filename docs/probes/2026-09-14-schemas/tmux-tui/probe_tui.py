#!/usr/bin/env python3
"""Shepherd schema probe: interactive Claude Code TUI under tmux (2026-09-14).

Re-run:  python3 docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py
Output:  docs/probes/2026-09-14-schemas/tmux-tui/run-<UTC stamp>/

SAFETY (see CLAUDE.md, spec section 18 incident):
  * every tmux call goes through tm(), which always passes -L shepherd-probe;
  * session names never contain ':'; pane targets are "=<name>:";
  * teardown is "tmux -L shepherd-probe kill-server" only;
  * the tmux server is started with a scrubbed environment (env -i) so the probe
    sessions do not inherit $TMUX / CLAUDECODE / messaging sockets of the caller;
  * hooks live only in throwaway dirs from mktemp under /tmp; cc10x plugin disabled there;
  * the only processes signalled are claude processes this script spawned.
"""
import datetime, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

SOCK = "shepherd-probe"
MODEL = "claude-haiku-4-5-20251001"
HERE = os.path.dirname(os.path.abspath(__file__))
STAMP = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
RUN = os.path.join(HERE, f"run-{STAMP}")
os.makedirs(RUN)
CLEAN_ENV = ["env", "-i", "HOME=/root", "PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
             "TERM=xterm-256color", "LANG=C.UTF-8"]
STEPLOG = open(os.path.join(RUN, "steps.log"), "a")


def log(msg):
    line = f"{datetime.datetime.utcnow().isoformat(timespec='milliseconds')}Z {msg}"
    print(line, flush=True)
    STEPLOG.write(line + "\n"); STEPLOG.flush()


def tm(*args, env_clean=False, check=True):
    assert "kill-server" not in args or args == ("kill-server",)
    cmd = (CLEAN_ENV if env_clean else []) + ["tmux", "-L", SOCK] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        log(f"tmux {args} rc={r.returncode} err={r.stderr.strip()}")
    return r


def save(name, text, mode="w"):
    p = os.path.join(RUN, name)
    with open(p, mode) as f:
        f.write(text)
    return p


def sleep(s):
    time.sleep(s)


def capture(sess, name, ansi=False, extra=()):
    args = ["capture-pane", "-p"] + (["-e"] if ansi else []) + list(extra) + ["-t", f"={sess}:"]
    out = tm(*args).stdout
    save(name, out)
    if ansi:  # printable rendering of the same bytes (cat -v) for quoting in markdown
        v = subprocess.run(["cat", "-v"], input=out.encode(), capture_output=True).stdout.decode()
        save(name + ".cat-v.txt", v)
    return out


def fmt(sess, fmtstr):
    return tm("display-message", "-p", "-t", f"={sess}:", fmtstr).stdout.strip()


def list_sessions(name):
    f = "#{session_name}|#{pane_pid}|#{pane_dead}|#{pane_dead_status}|#{pane_dead_signal}|#{alternate_on}|#{pane_width}x#{pane_height}|#{pane_title}"
    r = tm("list-sessions", "-F", f, check=False)
    save(name, f"# format: {f}\n# rc={r.returncode} stderr={r.stderr.strip()}\n{r.stdout}")
    return r.stdout


def hooks(logp):
    if not os.path.exists(logp):
        return []
    out = []
    for l in open(logp):
        try:
            out.append(json.loads(l))
        except Exception:
            out.append({"_event": "UNPARSEABLE", "payload": {}, "_raw": l})
    return out


def wait_event(logp, pred, timeout, after=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        hs = hooks(logp)
        for i, h in enumerate(hs[after:], start=after):
            if pred(h):
                return i, h
        sleep(0.5)
    return None, None


def ev(name, **kw):
    def p(h):
        if h.get("_event") != name:
            return False
        return all(h["payload"].get(k) == v for k, v in kw.items())
    return p


def send_text(sess, text):
    tm("send-keys", "-t", f"={sess}:", "-l", text)


def send_key(sess, key):
    tm("send-keys", "-t", f"={sess}:", key)


def sidecar(pid, name):
    p = f"/root/.claude/sessions/{pid}.json"
    txt = open(p).read() if os.path.exists(p) else f"<absent: {p}>"
    save(name, txt + "\n")
    return txt


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else "<absent>"


def spawn(sess, cwd, extra_args, logname):
    cmd = f"claude --model {MODEL} --debug-file {os.path.join(RUN, logname)} {extra_args}".strip()
    r = tm("new-session", "-d", "-s", sess, "-x", "160", "-y", "45", "-c", cwd, cmd, env_clean=True)
    tm("set-option", "-w", "-t", f"={sess}:", "remain-on-exit", "on")
    save(f"{sess}-spawn-cmd.txt", f"tmux -L {SOCK} new-session -d -s {sess} -x 160 -y 45 -c {cwd} '{cmd}'\nrc={r.returncode}\n")
    return int(fmt(sess, "#{pane_pid}") or 0)


def main():
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    tver = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
    save("versions.txt", f"claude --version: {ver}\ntmux -V: {tver}\nuname: {os.uname().sysname} {os.uname().release}\nrun: {STAMP}\n")
    log(f"versions {ver} / {tver}")
    pre = tm("ls", check=False)
    save("socket-precheck.txt", f"tmux -L {SOCK} ls -> rc={pre.returncode} out={pre.stdout!r} err={pre.stderr.strip()!r}\n")
    if pre.returncode == 0:
        log("probe socket already has sessions; refusing to run"); sys.exit(2)

    HLOG = os.path.join(RUN, "hooks-a.jsonl")      # project-settings hooks (dirA)
    HLOG_B = os.path.join(RUN, "hooks-b.jsonl")    # --settings hooks (dirB, trust refused)
    dirA = tempfile.mkdtemp(prefix="shp-tui-A-", dir="/tmp")
    dirB = tempfile.mkdtemp(prefix="shp-tui-B-", dir="/tmp")
    save("tmpdirs.txt", f"dirA={dirA}\ndirB={dirB}\n")
    subprocess.run([sys.executable, os.path.join(HERE, "make_settings.py"),
                    os.path.join(dirA, ".claude", "settings.json"), HLOG, ver], check=True)
    subprocess.run([sys.executable, os.path.join(HERE, "make_settings.py"),
                    os.path.join(RUN, "settings-b-flag.json"), HLOG_B, ver], check=True)
    for p in (os.path.join(dirA, ".claude", "settings.json"), os.path.join(RUN, "settings-b-flag.json")):
        d = json.load(open(p)); d["remoteControlAtStartup"] = False; json.dump(d, open(p, "w"), indent=1)
    shutil.copy(os.path.join(dirA, ".claude", "settings.json"), os.path.join(RUN, "settings-a-project.json"))

    try:
        # ---------------- 1. trust dialog -----------------------------------------
        log("1 spawn probe_a in untrusted dirA (hooks in project settings)")
        pidA = spawn("probe_a", dirA, "", "debug-a.log")
        sleep(6)
        capture("probe_a", "01-trust-dialog.txt")
        capture("probe_a", "01-trust-dialog.ansi", ansi=True)
        save("01-trust-dialog-fmt.txt", fmt("probe_a", "alternate_on=#{alternate_on} pane_pid=#{pane_pid} pane_dead=#{pane_dead} pane_title=#{pane_title} cursor=#{cursor_x},#{cursor_y}") + "\n")
        sidecar(pidA, "01-trust-dialog-sidecar.json")
        log("1b spawn probe_b in untrusted dirB (hooks via --settings)")
        pidB = spawn("probe_b", dirB, f"--settings {os.path.join(RUN, 'settings-b-flag.json')}", "debug-b.log")
        sleep(15)
        capture("probe_b", "01b-trust-dialog-b.txt")
        nA, nB = len(hooks(HLOG)), len(hooks(HLOG_B))
        save("01-hooks-before-trust.txt", f"after >=15s on the trust dialog: hooks-a lines={nA} (project settings), hooks-b lines={nB} (--settings)\n")
        log(f"hooks before trust: A={nA} B={nB}")
        # refuse trust on B: Enter on the default option ("No, exit")
        send_key("probe_b", "Enter"); sleep(4)
        list_sessions("01b-list-sessions-after-refuse.txt")
        capture("probe_b", "01b-after-refuse.txt")
        save("01b-hooks-b-after-refuse.txt", f"hooks-b lines={len(hooks(HLOG_B))}\n")
        # accept trust on A
        send_key("probe_a", "Down"); sleep(1)
        capture("probe_a", "01c-trust-yes-selected.txt")
        send_key("probe_a", "Enter")
        i, h = wait_event(HLOG, ev("SessionStart"), 40)
        log(f"SessionStart after trust: {h is not None}")
        sleep(3)
        capture("probe_a", "02-after-trust.txt")
        capture("probe_a", "02-after-trust.ansi", ansi=True)
        save("02-after-trust-fmt.txt", fmt("probe_a", "alternate_on=#{alternate_on} pane_title=#{pane_title} window_name=#{window_name}") + "\n")
        sidecar(pidA, "02-sidecar-after-trust.json")
        sid = h["payload"]["session_id"] if h else None
        tr = h["payload"]["transcript_path"] if h else None
        save("02-ids.txt", f"session_id={sid}\ntranscript_path={tr}\npane_pid={pidA}\n")

        # ---------------- 2. first prompt, Stop, suggestion ghost text ----------
        log("2 send-keys prompt at idle prompt")
        n0 = len(hooks(HLOG))
        send_text("probe_a", "Reply with only the word PONG")
        capture("probe_a", "03-typed-before-enter.txt")
        send_key("probe_a", "Enter")
        i, stop1 = wait_event(HLOG, ev("Stop"), 60, after=n0)
        sidecar(pidA, "03-sidecar-after-stop.json")
        wait_event(HLOG, ev("SubagentStop"), 20, after=i or n0)
        sleep(2)
        capture("probe_a", "03-after-stop.txt")
        capture("probe_a", "03-after-stop.ansi", ansi=True)

        # ---------------- 3. idle_prompt Notification ------------------------------
        log("3 wait for idle_prompt Notification")
        i, idle = wait_event(HLOG, ev("Notification", notification_type="idle_prompt"), 100, after=n0)
        if idle and stop1:
            save("04-idle-delay.txt", f"Stop epoch={stop1['_epoch']} Notification(idle_prompt) epoch={idle['_epoch']} delta_s={idle['_epoch']-stop1['_epoch']:.3f}\n")
        sidecar(pidA, "04-sidecar-idle.json")

        # ---------------- 3b. multi-line send-keys -l ------------------------------
        log("3b multi-line send-keys -l")
        n0 = len(hooks(HLOG))
        send_text("probe_a", "Reply with only the word MULTI.\n- note one\n- note two")
        sleep(2)
        capture("probe_a", "05-multiline-typed.txt")
        save("05-multiline-hooks-before-enter.txt", json.dumps([h["_event"] for h in hooks(HLOG)[n0:]]) + "\n")
        send_key("probe_a", "Enter")
        wait_event(HLOG, ev("Stop"), 60, after=n0)
        sleep(2)
        capture("probe_a", "05-multiline-after.txt")

        # ---------------- 4. permission prompt -------------------------------------
        log("4 permission prompt")
        n0 = len(hooks(HLOG))
        send_text("probe_a", "Use the Bash tool to run exactly this command: touch perm-probe.txt")
        send_key("probe_a", "Enter")
        i, pr = wait_event(HLOG, ev("PermissionRequest"), 60, after=n0)
        sleep(1)
        capture("probe_a", "06-permission-dialog.txt")
        capture("probe_a", "06-permission-dialog.ansi", ansi=True)
        sidecar(pidA, "06-sidecar-permission.json")
        i2, pn = wait_event(HLOG, ev("Notification", notification_type="permission_prompt"), 30, after=n0)
        if pr and pn:
            save("06-permission-delay.txt", f"PermissionRequest epoch={pr['_epoch']} Notification(permission_prompt) epoch={pn['_epoch']} delta_s={pn['_epoch']-pr['_epoch']:.3f}\n")
        send_key("probe_a", "Enter")  # default option "1. Yes"
        wait_event(HLOG, ev("Stop"), 60, after=n0)
        sleep(1)
        capture("probe_a", "06-permission-after.txt")

        # ---------------- 5. send-keys while the model is running -----------------
        log("5 send-keys while running")
        n0 = len(hooks(HLOG))
        send_text("probe_a", "Use the Bash tool to run exactly: sleep 12 ; then reply with only DONE-ONE")
        send_key("probe_a", "Enter")
        i, pre_t = wait_event(HLOG, ev("PreToolUse"), 60, after=n0)
        sleep(2)
        sidecar(pidA, "07-sidecar-running.json")
        capture("probe_a", "07-running-before-send.txt")
        save("07-send-time.txt", f"send epoch={time.time():.6f}\n")
        send_text("probe_a", "Reply with only the word SECOND")
        send_key("probe_a", "Enter")
        sleep(1.5)
        capture("probe_a", "07-running-after-send.txt")
        wait_event(HLOG, ev("Stop"), 90, after=n0)
        sleep(2)
        capture("probe_a", "07-after-stop.txt")
        stops = [h for h in hooks(HLOG)[n0:] if h["_event"] == "Stop"]
        save("07-stop-count.txt", f"Stop events in this step: {len(stops)}\n")

        # ---------------- 6. bare Enter on a suggestion ----------------------------
        log("6 bare Enter at idle prompt with suggestion")
        n0 = len(hooks(HLOG))
        wait_event(HLOG, ev("SubagentStop"), 20, after=max(0, n0 - 3))
        sleep(2)
        capture("probe_a", "08-prompt-with-suggestion.txt")
        capture("probe_a", "08-prompt-with-suggestion.ansi", ansi=True)
        send_key("probe_a", "Enter")
        sleep(6)
        capture("probe_a", "08-after-bare-enter.txt")
        save("08-hooks-after-bare-enter.txt", json.dumps([[h["_event"], h["payload"].get("prompt")] for h in hooks(HLOG)[n0:]]) + "\n")
        if any(h["_event"] == "PermissionRequest" for h in hooks(HLOG)[n0:]):
            send_key("probe_a", "Escape")
        wait_event(HLOG, ev("Stop"), 30, after=n0)
        sleep(2)

        # ---------------- 7. resize reflow ----------------------------------------
        log("7 resize")
        capture("probe_a", "09-resize-before-160x45.txt")
        tm("resize-window", "-t", f"=probe_a:", "-x", "70", "-y", "30")
        sleep(3)
        after = capture("probe_a", "09-resize-after-70x30.txt")
        capture("probe_a", "09-resize-after-70x30.ansi", ansi=True)
        widths = [len(l) for l in after.splitlines()]
        save("09-resize-fmt.txt", fmt("probe_a", "pane=#{pane_width}x#{pane_height} window=#{window_width}x#{window_height}") + f"\nmax captured line length={max(widths) if widths else 0} lines={len(widths)}\n")
        tm("resize-window", "-t", f"=probe_a:", "-x", "160", "-y", "45")
        sleep(2)

        # ---------------- 8. /rename -----------------------------------------------
        log("8 /rename")
        n0 = len(hooks(HLOG))
        L0 = sum(1 for _ in open(tr)) if tr and os.path.exists(tr) else 0
        save("10-rename-before-fmt.txt", fmt("probe_a", "pane_title=#{pane_title}") + "\n")
        sidecar(pidA, "10-sidecar-before-rename.json")
        send_text("probe_a", "/rename shp-probe-title-1")
        sleep(1)
        send_key("probe_a", "Enter")
        sleep(4)
        capture("probe_a", "10-rename-after.txt")
        save("10-rename-after-fmt.txt", fmt("probe_a", "pane_title=#{pane_title}") + "\n")
        sidecar(pidA, "10-sidecar-after-rename.json")
        lines = open(tr).read().splitlines()[L0:] if tr else []
        save("10-rename-transcript-new-lines.jsonl", "\n".join(lines) + "\n")
        save("10-rename-hooks.txt", f"hook events during /rename: {json.dumps([h['_event'] for h in hooks(HLOG)[n0:]])}\n")

        # ---------------- 9. /compact ----------------------------------------------
        log("9 /compact")
        n0 = len(hooks(HLOG))
        send_text("probe_a", "/compact")
        sleep(1)
        send_key("probe_a", "Enter")
        wait_event(HLOG, ev("PostCompact"), 120, after=n0)
        sleep(3)
        capture("probe_a", "11-compact-after.txt")
        save("11-compact-hook-order.txt", "\n".join(f"{h['_captured_at']} {h['_event']} {h['payload'].get('source') or h['payload'].get('trigger') or ''}" for h in hooks(HLOG)[n0:]) + "\n")

        # ---------------- 10. fork ---------------------------------------------------
        log("10 fork via --resume --fork-session in a second tmux session")
        projdir = os.path.dirname(tr)
        before = {"sha": sha(tr), "lines": sum(1 for _ in open(tr)), "files": sorted(os.listdir(projdir))}
        nF = len(hooks(HLOG))
        pidF = spawn("probe_fork", dirA, f"--resume {sid} --fork-session", "debug-fork.log")
        i, fs = wait_event(HLOG, lambda h: h["_event"] == "SessionStart" and h["payload"].get("session_id") != sid, 40, after=nF)
        fsid = fs["payload"]["session_id"] if fs else None
        ftr = fs["payload"]["transcript_path"] if fs else None
        sleep(3)
        mid = {"fork_transcript_exists_before_prompt": os.path.exists(ftr) if ftr else None, "files": sorted(os.listdir(projdir))}
        capture("probe_fork", "12-fork-started.txt")
        sidecar(pidF, "12-fork-sidecar.json")
        send_text("probe_fork", "Answer in one word: what word did you reply with in your very first reply?")
        send_key("probe_fork", "Enter")
        wait_event(HLOG, lambda h: h["_event"] == "Stop" and h["payload"].get("session_id") == fsid, 60, after=nF)
        sleep(3)
        capture("probe_fork", "12-fork-answer.txt")
        afterF = {"sha": sha(tr), "lines": sum(1 for _ in open(tr)), "files": sorted(os.listdir(projdir))}
        fstats = {}
        if ftr and os.path.exists(ftr):
            fl = [json.loads(l) for l in open(ftr)]
            fstats = {"lines": len(fl),
                      "sessionId_values": sorted({str(x.get("sessionId")) for x in fl}),
                      "keys_mentioning_fork": sorted({k for x in fl for k in x if "fork" in k.lower()}),
                      "types": sorted({str(x.get("type")) for x in fl})}
            save("12-fork-transcript-head3.jsonl", "".join(open(ftr).readlines()[:3]))
            forkish = [l for l in open(ftr) if '"forkedFrom"' in l][:2]
            save("12-fork-transcript-forkedFrom-sample.jsonl", "".join(forkish))
        a_events_during_fork = [[h["_event"], h["payload"].get("notification_type")] for h in hooks(HLOG)[nF:] if h["payload"].get("session_id") == sid]
        save("12-fork-summary.json", json.dumps({"original_session_id": sid, "fork_session_id": fsid,
              "original_transcript": tr, "fork_transcript": ftr,
              "before": before, "fork_started_no_prompt": mid, "after_fork_turn": afterF,
              "original_unchanged": before["sha"] == afterF["sha"], "fork_transcript_stats": fstats,
              "hook_events_for_original_session_during_fork": a_events_during_fork}, indent=1) + "\n")

        # ---------------- 11. /exit on fork ----------------------------------------
        log("11 /exit on fork")
        n0 = len(hooks(HLOG))
        send_text("probe_fork", "/exit")
        sleep(1)
        send_key("probe_fork", "Enter")
        wait_event(HLOG, ev("SessionEnd"), 20, after=n0)
        sleep(3)
        list_sessions("13-list-sessions-after-exit.txt")
        capture("probe_fork", "13-dead-pane.txt")
        sidecar(pidF, "13-fork-sidecar-after-exit.json")

        # ---------------- 12. SIGTERM a claude we spawned ----------------------------
        log("12 spawn probe_sig in trusted dirA and SIGTERM it")
        n0 = len(hooks(HLOG))
        pidS = spawn("probe_sig", dirA, "", "debug-sig.log")
        wait_event(HLOG, lambda h: h["_event"] == "SessionStart" and h["payload"].get("session_id") not in (sid, fsid), 40, after=n0)
        sleep(3)
        comm = open(f"/proc/{pidS}/comm").read().strip()
        save("14-sig-target.txt", f"pane_pid={pidS} comm={comm}\n")
        if comm == "claude":
            os.kill(pidS, 15)
        sleep(5)
        list_sessions("14-list-sessions-after-sigterm.txt")
        save("14-hooks-after-sigterm.txt", json.dumps([[h["_event"], h["payload"].get("reason")] for h in hooks(HLOG)[n0:]]) + "\n")

        # ---------------- 13. kill-session on the original --------------------------
        log("13 kill-session probe_a")
        n0 = len(hooks(HLOG))
        tm("kill-session", "-t", "=probe_a")
        sleep(6)
        list_sessions("15-list-sessions-after-kill.txt")
        save("15-hooks-after-kill.txt", json.dumps([[h["_event"], h["payload"].get("reason"), h["payload"].get("session_id")] for h in hooks(HLOG)[n0:]]) + "\n")
        save("15-pid-after-kill.txt", f"/proc/{pidA} exists: {os.path.exists(f'/proc/{pidA}')}\nsidecar exists: {os.path.exists(f'/root/.claude/sessions/{pidA}.json')}\n")
        fin = hooks(HLOG)
        save("hooks-a-event-sequence.txt", "\n".join(f"{h['_captured_at']} {h['payload'].get('session_id','')[:8]} {h['_event']} {h['payload'].get('notification_type') or h['payload'].get('source') or h['payload'].get('reason') or h['payload'].get('trigger') or ''}" for h in fin) + "\n")
    finally:
        log("teardown: tmux -L shepherd-probe kill-server")
        tm("kill-server", check=False)
        r = tm("ls", check=False)
        save("teardown.txt", f"after kill-server: tmux -L {SOCK} ls rc={r.returncode} err={r.stderr.strip()}\n")


if __name__ == "__main__":
    main()
