#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14).
Part pidfd (spec 938, 964 "observed process exit", also for attached sessions Shepherd did not spawn):
  watch a claude process that is NOT our child (it is a tmux pane, child of the tmux server) with os.pidfd_open + poll;
  what exit information is available to a non-parent (waitid on the pidfd, /proc, tmux pane_dead_status)?
Part pty (spec 1144-1145 fallback PtyRunner): run the Claude Code TUI under Python pty.fork: terminal modes it
  enables, resize via TIOCSWINSZ, a turn, /exit, exit status; and closing the master fd (hangup).
Backend for turns: mock_api2.py + isolated CLAUDE_CONFIG_DIR.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py
"""
import errno, fcntl, json, os, pty, re, select, signal, struct, subprocess, sys, termios, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import *

R = Run("pidfd-pty")
SOCK = "shp-gap-pidfd"
assert tm(SOCK, "ls").returncode != 0
mock = MockEnv(R, "pidfd")
res = {"kernel": os.uname().release}


def starttime(pid):
    return int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19])


def watch(pid, action, label, timeout=30):
    info = {"pid": pid, "ppid": int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1]),
            "comm": open(f"/proc/{pid}/comm").read().strip(), "starttime": starttime(pid), "is_our_child": False}
    info["parent_comm"] = open(f"/proc/{info['ppid']}/comm").read().strip()
    fd = os.pidfd_open(pid)
    try:
        signal.pidfd_send_signal(fd, 0); info["pidfd_send_signal_0"] = "ok"
    except Exception as e:
        info["pidfd_send_signal_0"] = repr(e)
    p = select.poll(); p.register(fd, select.POLLIN)
    info["poll_before"] = p.poll(0)
    t0 = time.time(); action()
    ev_ = p.poll(timeout * 1000)
    info["poll_after_ms"] = round((time.time() - t0) * 1000, 1)
    info["poll_events"] = [(f, e) for f, e in ev_]
    try:
        r = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG)
        info["waitid_P_PIDFD"] = repr(r)
    except Exception as e:
        info["waitid_P_PIDFD"] = f"{type(e).__name__}: errno={getattr(e, 'errno', None)} {e}"
    try:
        signal.pidfd_send_signal(fd, 0); info["pidfd_send_signal_0_after"] = "ok"
    except Exception as e:
        info["pidfd_send_signal_0_after"] = f"{type(e).__name__}: errno={getattr(e, 'errno', None)}"
    info["proc_exists_after"] = os.path.exists(f"/proc/{pid}")
    os.close(fd)
    res[label] = info
    R.log(f"{label}: {json.dumps(info)}")


try:
    # ---------------------------------------------------------------------------------- pidfd
    for label, how in (("pidfd_exit_via_trust_refusal", "refuse"), ("pidfd_tmux_kill_session", "kill")):
        d = os.path.join(mock.root, label); os.makedirs(d)
        t = Tui(R, SOCK, f"shepherd_{label[:20]}", d, ["claude", "--model", HAIKU], extra_env=mock.env_list())
        t.wait_screen("trust this folder", 25)
        cpid = claude_pid_under(t.pane_pid)
        if how == "refuse":
            watch(cpid, lambda: t.keys("Enter"), label)       # default option "No, exit"
            time.sleep(1)
            res[label]["tmux_pane_after"] = t.fmt("dead=#{pane_dead} status=#{pane_dead_status} signal=#{pane_dead_signal}")
        else:
            watch(cpid, t.kill, label)
            res[label]["tmux_session_after"] = tm(SOCK, "has-session", "-t", f"={t.name}").stderr.strip()
    # a setsid-detached process we started (so it is not our child either), terminated with SIGTERM
    spid = int(subprocess.run(["sh", "-c", "setsid sleep 312.345 >/dev/null 2>&1 & echo $!"], capture_output=True, text=True).stdout.strip())
    time.sleep(0.5)
    if open(f"/proc/{spid}/cmdline").read() == "sleep\x00312.345\x00":
        watch(spid, lambda: os.kill(spid, signal.SIGTERM), "pidfd_setsid_sleep_sigterm", 10)

    # ---------------------------------------------------------------------------------- pty
    d = os.path.join(mock.root, "pty"); os.makedirs(os.path.join(d, ".claude"))
    HL = R.path("pty-hooks.jsonl")
    write_json(os.path.join(d, ".claude", "settings.json"), settings_obj(HL, R.ver, events=["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"]))
    stream = open(R.path("pty-stream.bin"), "wb")
    env = mock.env_dict(); env["TERM"] = "xterm-256color"

    def spawn_pty(cols, rows):
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(d)
            os.execvpe("claude", ["claude", "--model", HAIKU], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        return pid, fd

    def pump(fd, seconds, until=None):
        buf = b""; t0 = time.time()
        while time.time() - t0 < seconds:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                try:
                    b = os.read(fd, 65536)
                except OSError as e:
                    if e.errno == errno.EIO:
                        return buf, "EIO"
                    raise
                if not b:
                    return buf, "EOF"
                buf += b; stream.write(b); stream.flush()
                if until and until in buf:
                    return buf, "found"
        return buf, "timeout"

    pid, fd = spawn_pty(120, 36)
    b0, st = pump(fd, 20, b"trust this folder")
    pty_info = {"initial_bytes": len(b0), "trust_dialog": st}
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0)); os.kill(pid, signal.SIGWINCH)
    b1, _ = pump(fd, 2)
    pty_info["bytes_after_resize_100x30"] = len(b1)
    os.write(fd, b"\x1b[B"); time.sleep(0.5); os.write(fd, b"\r")
    b2, st2 = pump(fd, 20, b"for shortcuts")
    pty_info["after_trust"] = st2
    os.write(fd, b"hello from pty"); time.sleep(0.5); os.write(fd, b"\r")
    b3, st3 = pump(fd, 20, b"OK-MOCK")
    pty_info["turn"] = st3
    time.sleep(2); pump(fd, 1)
    os.write(fd, b"/exit"); time.sleep(0.5); os.write(fd, b"\r")
    b4, st4 = pump(fd, 15)
    wpid, status = os.waitpid(pid, 0)
    pty_info["exit"] = {"read_end": st4, "waitpid_status": status, "exitstatus": os.waitstatus_to_exitcode(status)}
    allb = b0 + b1 + b2 + b3 + b4
    modes = {}
    for m in re.finditer(rb"\x1b\[\?([0-9;]+)([hl])", allb):
        modes.setdefault(m.group(1).decode(), set()).add(m.group(2).decode())
    pty_info["dec_private_modes_seen"] = {k: sorted(v) for k, v in sorted(modes.items())}
    pty_info["total_bytes"] = len(allb)
    pty_info["hooks"] = [h["_event"] + (f"[{h['payload'].get('reason')}]" if h["payload"].get("reason") else "") for h in hooks(HL)]
    res["pty_turn_and_exit"] = pty_info
    R.log(f"pty: {json.dumps(pty_info)}")
    # second pty: close the master fd while claude is idle (hangup)
    n = len(hooks(HL))
    pid, fd = spawn_pty(120, 36)
    b5, st5 = pump(fd, 20, b"for shortcuts")
    time.sleep(2); pump(fd, 1)
    t0 = time.time(); os.close(fd)
    for _ in range(100):
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid:
            break
        time.sleep(0.1)
    res["pty_master_closed"] = {"ready": st5, "waitpid": [wpid, status],
                                "decoded": (f"exitcode={os.waitstatus_to_exitcode(status)}" if wpid else "still running after 10s"),
                                "seconds": round(time.time() - t0, 2),
                                "hooks": [h["_event"] + (f"[{h['payload'].get('reason')}]" if h["payload"].get("reason") else "") for h in hooks(HL)[n:]]}
    if not wpid:
        os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
    R.log(f"pty_master_closed: {res['pty_master_closed']}")
finally:
    R.save("results.json", json.dumps(res, indent=1, default=list))
    tm(SOCK, "kill-server", run=R)
    mock.close()
print(json.dumps(res, indent=1, default=list))
