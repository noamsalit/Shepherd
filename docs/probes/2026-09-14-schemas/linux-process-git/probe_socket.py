#!/usr/bin/env python3
"""Shepherd linux-process-git probe: Unix domain socket at mode 0600 + SO_PEERCRED (2026-09-14).

Re-run: python3 docs/probes/2026-09-14-schemas/linux-process-git/probe_socket.py

All sockets live in a mktemp -d directory under /tmp. Checks:
 1. umask-at-bind gives a 0600 socket with no chmod window; plain bind gives the umask default.
 2. SO_PEERCRED from Python returns (pid, uid, gid) of the connecting process; pid is verified.
 3. A different uid (nobody, via runuser) is refused by the 0600 socket and by the 0700 dir.
 4. sun_path length limit (what happens with a long $XDG_RUNTIME_DIR path).
 5. Abstract-namespace sockets have no file mode (so 0600 cannot protect them).
 6. A stale socket file after the listener exits: connect() error, and bind() error on restart.
Writes captures/socket.txt.
"""
import os, socket, struct, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "captures", "socket.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
lines = []


def log(*a):
    lines.append(" ".join(str(x) for x in a))


log("claude_version:", subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip())
log("date_utc:", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
log("python:", sys.version.split()[0], "umask_now:", oct(os.umask(0o022)))
T = tempfile.mkdtemp(prefix="shp-lpg-sock.", dir="/tmp")
os.chmod(T, 0o755)  # parent reachable by nobody so the socket's own mode is what is tested
D = os.path.join(T, "shepherd")
os.mkdir(D, 0o700)
os.chmod(D, 0o700)
log("tmpdir:", T)

# 1. modes
p_plain = os.path.join(T, "plain.sock")
s_plain = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s_plain.bind(p_plain); s_plain.listen(1)
old = os.umask(0o177)
p_600 = os.path.join(T, "sessiond.sock")
s600 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s600.bind(p_600)
os.umask(old)
s600.listen(4)
p_in700 = os.path.join(D, "sessiond.sock")
old = os.umask(0o177)
s700 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s700.bind(p_in700); s700.listen(4)
os.umask(old)
log("\n## 1. file modes (stat)")
log(subprocess.run(["stat", "-c", "%A %a %F %U:%G %n", p_plain, p_600, D, p_in700], capture_output=True, text=True).stdout.rstrip())
log("ls -la:")
log(subprocess.run(["ls", "-la", T, D], capture_output=True, text=True).stdout.rstrip())

# 2. SO_PEERCRED
log("\n## 2. SO_PEERCRED")
child = subprocess.Popen([sys.executable, "-c",
    "import socket,sys,time;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall(b'hi');time.sleep(0.5)", p_600])
c, _ = s600.accept()
raw = c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
pid, uid, gid = struct.unpack("3i", raw)
log("getsockopt raw bytes:", raw.hex(), "len", len(raw))
log("peer (pid, uid, gid):", (pid, uid, gid), "| Popen child pid:", child.pid, "| match:", pid == child.pid)
log("socket.SO_PEERCRED constant:", socket.SO_PEERCRED, "| hasattr(socket,'SCM_CREDENTIALS'):", hasattr(socket, "SCM_CREDENTIALS"))
c.recv(16); c.close(); child.wait()
# peer pid after the peer has exited: SO_PEERCRED is captured at connect() time
child2 = subprocess.Popen([sys.executable, "-c",
    "import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall(b'bye')", p_600])
child2.wait()
c, _ = s600.accept()
pid2 = struct.unpack("3i", c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0]
log("peer exited BEFORE accept(): SO_PEERCRED pid =", pid2, "| child pid:", child2.pid,
    "| /proc/<pid> exists now:", os.path.exists(f"/proc/{pid2}"))
c.close()

# 3. other uid
log("\n## 3. connect as uid nobody (runuser -u nobody)")
probe = "import socket,sys\ns=socket.socket(socket.AF_UNIX)\ntry:\n s.connect(sys.argv[1]); print('connected')\nexcept Exception as e: print(type(e).__name__, e)"
for label, path in (("plain.sock (umask 022 default)", p_plain), ("sessiond.sock (0600)", p_600), ("0600 sock inside 0700 dir", p_in700)):
    r = subprocess.run(["runuser", "-u", "nobody", "--", sys.executable, "-c", probe, path], capture_output=True, text=True)
    log(f"{label}:", (r.stdout + r.stderr).strip().replace(T, "<tmpdir>"))

# 4. sun_path limit
log("\n## 4. sun_path length limit")
for n in (107, 108):
    base = os.path.join(T, "L")
    p = base + "x" * (n - len(base))
    s = socket.socket(socket.AF_UNIX)
    try:
        s.bind(p); log(f"path len {len(p)} bytes: bind ok")
    except OSError as e:
        log(f"path len {len(p)} bytes: {type(e).__name__}: {e}")
    s.close()
    if os.path.exists(p):
        os.unlink(p)

# 5. abstract namespace
log("\n## 5. abstract namespace socket")
sa = socket.socket(socket.AF_UNIX); sa.bind("\0shp-lpg-probe-%d" % os.getpid()); sa.listen(1)
log("bound abstract name; filesystem entry: none; /proc/net/unix line:",
    [l.strip() for l in open("/proc/net/unix") if "shp-lpg-probe-%d" % os.getpid() in l])
r = subprocess.run(["runuser", "-u", "nobody", "--", sys.executable, "-c",
    "import socket,sys\ns=socket.socket(socket.AF_UNIX)\ntry:\n s.connect(sys.argv[1].replace('@','\\0',1)); print('connected')\nexcept Exception as e: print(type(e).__name__, e)",
    "@shp-lpg-probe-%d" % os.getpid()], capture_output=True, text=True)
log("connect as nobody to abstract name:", (r.stdout + r.stderr).strip())
sa.close()

# 6. stale socket
log("\n## 6. stale socket file after listener close")
s600.close()
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(p_600); log("connect: ok")
except OSError as e:
    log(f"connect to stale path: {type(e).__name__}: {e}".replace(T, "<tmpdir>"))
s = socket.socket(socket.AF_UNIX)
try:
    s.bind(p_600); log("re-bind: ok")
except OSError as e:
    log(f"re-bind same path without unlink: {type(e).__name__}: {e}".replace(T, "<tmpdir>"))
for x in (s_plain, s700):
    x.close()
subprocess.run(["rm", "-rf", T])
open(OUT, "w").write("\n".join(lines) + "\n")
print(OUT)
