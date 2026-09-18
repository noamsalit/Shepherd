"""Shared helpers for the Shepherd gap-fill probes (2026-09-14).

SAFETY (CLAUDE.md, spec section 18 incident):
  * tm(sock, ...) always passes -L <sock>; sock must start with "shp-gap"; kill-server is
    only allowed on such a socket.
  * session names never contain ':'; targets use "=<name>:".
  * tmux servers are started under env -i, so panes never inherit the caller's $TMUX,
    CLAUDECODE or Remote Control bridge variables.
  * hooks/settings live only under mktemp dirs in /tmp; cc10x plugin disabled there;
    remoteControlAtStartup false.
  * only processes these scripts started are ever signalled.
"""
import datetime, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "capture_hook.sh")
HAIKU = "claude-haiku-4-5-20251001"
EVENTS = ["PreToolUse", "PostToolUse", "PostToolUseFailure", "PostToolBatch", "Notification",
          "UserPromptSubmit", "UserPromptExpansion", "SessionStart", "SessionEnd", "Stop", "StopFailure",
          "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "PreModelSwitch", "PostModelSwitch",
          "PermissionRequest", "PermissionDenied", "Setup", "TeammateIdle", "TaskCreated", "TaskCompleted",
          "Elicitation", "ElicitationResult", "ConfigChange", "WorktreeCreate", "WorktreeRemove",
          "InstructionsLoaded", "CwdChanged", "FileChanged", "DirectoryAdded", "MessageDisplay"]
PATHV = "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
CLEAN_ENV = ["env", "-i", "HOME=/root", f"PATH={PATHV}", "TERM=xterm-256color", "LANG=C.UTF-8"]


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def claude_version(binary="claude"):
    return subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()


class Run:
    def __init__(self, name):
        self.dir = os.path.join(HERE, f"{name}-{stamp()}")
        os.makedirs(self.dir)
        self.steplog = open(os.path.join(self.dir, "steps.log"), "a")
        self.ver = claude_version()
        tv = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
        self.save("versions.txt", f"claude --version: {self.ver}\ntmux -V: {tv}\nuname: {os.uname().sysname} {os.uname().release}\npython: {sys.version.split()[0]}\nrun: {os.path.basename(self.dir)}\n")

    def log(self, msg):
        line = f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')} {msg}"
        print(line, flush=True)
        self.steplog.write(line + "\n"); self.steplog.flush()

    def path(self, name):
        return os.path.join(self.dir, name)

    def save(self, name, text, mode="w"):
        p = self.path(name)
        with open(p, mode) as f:
            f.write(text)
        return p


def tm(sock, *args, env_clean=False, check=False, run=None):
    assert sock.startswith("shp-gap"), sock
    cmd = (CLEAN_ENV if env_clean else []) + ["tmux", "-L", sock] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if run is not None:
        run.log(f"$ tmux -L {sock} {' '.join(args)} -> rc={r.returncode} out={r.stdout.strip()[:300]!r} err={r.stderr.strip()[:300]!r}")
    return r


def fmt(sock, sess, f):
    return tm(sock, "display-message", "-p", "-t", f"={sess}:", f).stdout.strip()


def settings_obj(hooklog, ver, events=None, marker=False, extra=None):
    hooks = {}
    for ev in (events or EVENTS):
        e = {"type": "command", "command": f"SHP_CLAUDE_VERSION='{ver}' {CAP} {ev} {hooklog}", "timeout": 10}
        if marker:
            e["_shepherd_managed"] = True
        hooks[ev] = [{"hooks": [e]}]
    s = {"enabledPlugins": {"cc10x@cc10x": False}, "remoteControlAtStartup": False, "hooks": hooks}
    if extra:
        s.update(extra)
    return s


def write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(obj, f, indent=1)
    return p


def mktmp(tag):
    return tempfile.mkdtemp(prefix=f"shp-gap-{tag}-", dir="/tmp")


def hooks(logp):
    out = []
    if not os.path.exists(logp):
        return out
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
        time.sleep(0.4)
    return None, None


def ev(name, **kw):
    def p(h):
        if h.get("_event") != name:
            return False
        pl = h.get("payload") or {}
        return all(pl.get(k) == v for k, v in kw.items())
    return p


def wait_screen(sock, sess, needle, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = tm(sock, "capture-pane", "-p", "-t", f"={sess}:").stdout
        if needle in s:
            return s
        time.sleep(0.5)
    return None


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else "<absent>"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def ancestry(pid):
    out = []
    while pid > 1:
        try:
            st = open(f"/proc/{pid}/status").read()
        except Exception:
            break
        d = dict(l.split(":\t", 1) for l in st.splitlines() if ":\t" in l)
        out.append({"pid": pid, "comm": d.get("Name", "").strip()})
        pid = int(d.get("PPid", "0"))
    return out


def trust_accept(sock, sess, run, timeout=25):
    """If the workspace-trust dialog is on screen, choose 'Yes, I trust this folder'."""
    s = wait_screen(sock, sess, "trust this folder", timeout)
    if s is None:
        run.log(f"{sess}: no trust dialog seen within {timeout}s")
        return False
    tm(sock, "send-keys", "-t", f"={sess}:", "Down"); time.sleep(0.7)
    tm(sock, "send-keys", "-t", f"={sess}:", "Enter")
    run.log(f"{sess}: trust dialog accepted")
    return True


# ----------------------------------------------------------------------------------------------
# Mock API + isolated CLAUDE_CONFIG_DIR, and a tmux-hosted TUI session driver
FAKE_KEY = "sk-ant-api03-shp-fake-key-for-mock"


class MockEnv:
    """Local mock Messages API + isolated CLAUDE_CONFIG_DIR (never the user's ~/.claude)."""

    def __init__(self, run, tag, rules=None):
        import signal as _s
        self.run = run
        self.root = mktmp(tag)
        self.cfg = os.path.join(self.root, "cfg"); os.makedirs(self.cfg)
        self.work = os.path.join(self.root, "w"); os.makedirs(os.path.join(self.work, ".claude"))
        write_json(os.path.join(self.cfg, ".claude.json"),
                   {"hasCompletedOnboarding": True, "theme": "dark",
                    "customApiKeyResponses": {"approved": [FAKE_KEY[-20:]], "rejected": []}})
        self.rules_path = run.path(f"{tag}-rules.json")
        self.set_rules(rules or {"rules": [], "default_text": "OK-MOCK"})
        self.reqlog = run.path(f"{tag}-mock-requests.jsonl")
        self.port = free_port()
        self.srv = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_api2.py"), str(self.port), self.rules_path, self.reqlog],
                                    start_new_session=True)
        time.sleep(0.8)
        run.log(f"MockEnv {tag}: root={self.root} port={self.port}")

    def set_rules(self, rules):
        with open(self.rules_path, "w") as f:
            json.dump(rules, f, indent=1)

    def env_list(self):
        return [f"CLAUDE_CONFIG_DIR={self.cfg}", f"ANTHROPIC_API_KEY={FAKE_KEY}", f"ANTHROPIC_BASE_URL=http://127.0.0.1:{self.port}",
                "CLAUDE_CODE_MAX_RETRIES=0", "DISABLE_AUTOUPDATER=1", "DISABLE_TELEMETRY=1"]

    def env_dict(self):
        e = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k.startswith("ANTHROPIC") or k in ("TMUX", "TMUX_PANE"))}
        e.update(dict(x.split("=", 1) for x in self.env_list()))
        return e

    def requests(self):
        return [json.loads(l) for l in open(self.reqlog)] if os.path.exists(self.reqlog) else []

    def close(self):
        import signal as _s
        try:
            os.killpg(self.srv.pid, _s.SIGTERM)
        except Exception:
            pass


class Tui:
    """A Claude Code TUI in a throwaway tmux socket. argv is passed to tmux as separate words (no shell)."""

    def __init__(self, run, sock, name, cwd, argv, extra_env=(), x=140, y=40, remain=True):
        assert ":" not in name and "." not in name
        self.run, self.sock, self.name, self.t = run, sock, name, f"={name}:"
        envl = CLEAN_ENV + list(extra_env)
        # tmux gives a new pane the SERVER's environment, not the calling client's: pass per-session vars with -e too.
        eflags = [w for kv in extra_env for w in ("-e", kv)]
        r = subprocess.run(envl + ["tmux", "-L", sock, "new-session", "-d", "-s", name, "-x", str(x), "-y", str(y), "-c", cwd] + eflags + list(argv),
                           capture_output=True, text=True)
        run.log(f"spawn {name}: argv={argv} rc={r.returncode} err={r.stderr.strip()}")
        if remain:
            tm(sock, "set-option", "-w", "-t", self.t, "remain-on-exit", "on")
        time.sleep(0.5)
        self.pane_pid = int(self.fmt("#{pane_pid}") or 0)

    def fmt(self, f):
        return tm(self.sock, "display-message", "-p", "-t", self.t, f).stdout.strip()

    def keys(self, *k):
        tm(self.sock, "send-keys", "-t", self.t, *k, run=self.run)

    def text(self, s):
        tm(self.sock, "send-keys", "-t", self.t, "-l", s, run=self.run)

    def paste(self, s, fname):
        p = self.run.save(fname, s)
        tm(self.sock, "load-buffer", "-b", "shpgap", p)
        tm(self.sock, "paste-buffer", "-p", "-b", "shpgap", "-t", self.t, run=self.run)

    def submit(self, s, pause=0.4):
        self.text(s); time.sleep(pause); self.keys("Enter")

    def screen(self, ansi=False):
        a = ["capture-pane", "-p"] + (["-e"] if ansi else []) + ["-t", self.t]
        return tm(self.sock, *a).stdout

    def save_screen(self, fname):
        self.run.save(fname, self.screen())

    def wait_screen(self, needle, timeout):
        return wait_screen(self.sock, self.name, needle, timeout)

    def trust(self, timeout=25):
        return trust_accept(self.sock, self.name, self.run, timeout)

    def kill(self):
        tm(self.sock, "kill-session", "-t", f"={self.name}", run=self.run)


def claude_pid_under(pid):
    """pane_pid may be claude itself (argv spawn) or a shell whose child is claude."""
    try:
        if open(f"/proc/{pid}/comm").read().strip() == "claude":
            return pid
    except Exception:
        return None
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                st = open(f"/proc/{d}/stat").read()
                ppid = int(st.rsplit(")", 1)[1].split()[1])
                if ppid == pid and open(f"/proc/{d}/comm").read().strip() == "claude":
                    return int(d)
            except Exception:
                pass
    return None


def transcript_state(path):
    if not path or not os.path.exists(path):
        return {"path": path, "exists": False}
    b = open(path, "rb").read()
    return {"path": path, "size": len(b), "lines": b.count(b"\n"), "sha256": hashlib.sha256(b).hexdigest(),
            "ends_with_newline": b.endswith(b"\n")}
