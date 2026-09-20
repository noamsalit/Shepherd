# Probe — macOS G1 capture: `sun_path` budget, netcat flag set, runtime dir (2026-09-20)

**Question.** G1 (`docs/plans/2026-09-16-m1-foundation-visibility-plan.md` l.632) and assumption
A12 (l.736) say every `MacHost` value is `inferred`, "falsified by the first run on a Mac". This is
that run. It closes three of G1's five items by measurement and leaves two open.

**Host.** macOS 26.6.2 (build 25G83), Darwin 25.6.0, arm64 (`uname -a`, `sw_vers`).
`/usr/bin/nc` (Apple netcat), `/usr/bin/perl` 5.34.1. **`timeout` and `gtimeout` do not exist**
(`command -v timeout` → not found; `command -v gtimeout` → not found).
`TMPDIR=/var/folders/1c/mgs46bfj23zd342sscpd8r_80000gn/T/` (47 bytes).
Python 3.13.12, `.venv/bin/python`.

**Status:** verified live 2026-09-20 on this host. Every number below was measured here.

---

## Result 1 — `sun_path` is 104 bytes including the NUL, so the usable budget is 103

Bound a real `AF_UNIX` `SOCK_STREAM` socket at each length under `/tmp/shpprobe/`:

| path bytes | `bind()` |
|---|---|
| 100 | OK |
| 101 | OK |
| 102 | OK |
| **103** | **OK** |
| **104** | **`OSError: AF_UNIX path too long`** |
| 105 | `OSError: AF_UNIX path too long` |
| 106 | `OSError: AF_UNIX path too long` |
| 107 | `OSError: AF_UNIX path too long` |

`MAC_SOCKET_PATH_BUDGET = 103` (D55) is **correct**, and it is now measured rather than inferred.
Note the consequence for the contract suite: 107 — the Linux budget, E19 — does *not* bind here, so
`test_socket_path_budget_enforced`'s "the kernel agrees" half must ask the running platform's driver
for its budget instead of asserting the Linux constant against this kernel.

Reproduce:

```python
import os, socket
base = "/tmp/shpprobe/"; os.makedirs(base, exist_ok=True)
for n in (103, 104):
    p = base + "a" * (n - len(base))
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(p); print(n, "OK"); os.unlink(p)
    except OSError as e:
        print(n, "FAIL", e)
    finally:
        s.close()
```

## Result 2 — the netcat flag set, measured against a real listening socket

Apple's `nc` is not OpenBSD's. `nc -h` on this host has **no `-q`** and no OpenBSD `-N`
(`-N` here is `--apple-tcp-adp-wtimo num_probes`, which takes an argument, so `nc -N -U …` dies with
`nc: invalid tcp adaptive write timeout value` and delivers nothing). `-w secs` is
"Timeout for connects and final net reads".

Each candidate was run through `/bin/sh -c` with the payload on stdin against a real
`AF_UNIX` listener in three states: a normal reader, a reader that accepts and never reads
("hung `sessiond`", the case `timeout 0.25` guards on Linux), and no listener at all.

| candidate | 86 B frame | 40 KB frame | hung listener, small | hung listener, 40 KB |
|---|---|---|---|---|
| `nc -U` | 10/10 delivered, 8.7 ms median | 5/5 complete, 7.6 ms | **unbounded** (30 s observed) | **unbounded** |
| `nc -U -w 1` | 10/10, 10.8 ms | 5/5 complete | 1031 ms | **unbounded** |
| `nc -U -w 0` | 10/10, 8.2 ms | **TRUNCATED to 16 384 / 16 896 / 17 920 of 40 011 bytes, 3/3** | 27 ms | 27 ms |
| **`perl -MTime::HiRes=alarm -e 'alarm 0.25; exec @ARGV or exit 0' nc -U`** | **10/10, 15.8 ms** | **5/5 complete, 14.7 ms** | **264 ms** | **324 ms** |

Three findings, in order of how much they matter:

1. **`-w 0` is not the macOS `-q0`.** It is the trap. It looks right — it bounds the hung case at
   27 ms and delivers small frames 10/10 — and it silently drops more than half of a 40 KB frame.
   That is E34's failure mode exactly ("it still delivers, so the bug is silent"), one flag to the
   left. `-w 0` must never be written into a hook.
2. **No `nc` flag bounds a blocked write.** `-w` bounds connects and final net reads, not the write.
   With a peer that accepts and never reads, a frame larger than the socket buffer
   (`net.local.stream.sendspace` = 8192) blocks `nc` for as long as the peer stays wedged. The
   Linux command does not rely on `nc` for this either — that is what `timeout 0.25` is for.
3. **`perl` is the stock-macOS replacement for `timeout`.** `/usr/bin/perl` is present;
   `Time::HiRes` is core, so the bound can be sub-second where `alarm`'s integer seconds could not;
   an `alarm` timer survives `execve`, so the bound applies to `nc` and not to perl's own start-up;
   `exec @ARGV` with a list is `execvp`, so no second shell parses the socket path; and
   `or exit 0` plus the existing `|| true` keep the hook's exit status 0 (principle 4, C-1)
   whether the exec fails or `SIGALRM` kills `nc`.

The measured cost of the wrapper is **≈7 ms per invocation** (8.7 → 15.8 ms median). The bound it
buys is 264–324 ms against a wedged `sessiond`, versus unbounded. Both numbers sit far below the
5 s `HOOK_ENTRY_TIMEOUT_S` the settings entry carries (E18).

## Result 3 — `MAC_RUNTIME_ENV = "TMPDIR"` holds, with 34 bytes of headroom

`TMPDIR` on this host is `/var/folders/1c/mgs46bfj23zd342sscpd8r_80000gn/T/` — 47 bytes. The
control-socket path a real install composes from it is

```
/var/folders/1c/mgs46bfj23zd342sscpd8r_80000gn/T/Shepherd/sessiond.sock
```

which is **69 bytes against a budget of 103**. So the concern that a `TMPDIR`-derived runtime dir
might not leave room for a socket on a real install **does not hold on this host**: it fits with
34 bytes to spare. `MAC_RUNTIME_ENV` stays `TMPDIR`. The residual risk is a host whose
`DARWIN_USER_TEMP_DIR` is materially longer than this one's; `plan_socket()` already refuses that
case before bind with `SocketPathTooLong`, which is the honest failure.

## Result 4 — the hook costs 14-16 ms here, and Linux's 10 ms budget is not portable

`tests/engines/test_hookd_runtime.py::test_hookd_latency_under_10ms` measures the installed
command end to end (`sh -c`, payload on stdin, exit), 25 invocations per attempt, 3 attempts.
On this host, over 12 attempts:

```
14.83  14.20  14.08
15.53  14.34  14.07
15.53  14.22  15.03
16.23  15.12  14.43   (ms per invocation)
```

Linux measured 3.4 ms for the same shape. Almost none of the difference is the `perl` bound:

| | this Mac | Linux (`2026-09-16-hookd-latency.md`) |
|---|---|---|
| `sh -c true` | 4.19 ms | ~1 ms |
| `perl -e 0` | 3.56 ms | — |
| `python3 -c pass` | 26.11 ms | — |
| the installed hook | **14-16 ms** | **3.4 ms** |
| a Python dispatcher | ≥26 ms | 31.7 ms |

Two things follow, and the second is the one that matters.

1. **Process spawn is dearer on macOS.** `sh -c true` alone is four times its Linux cost, before
   `nc` or `perl` is involved. The `perl` bound adds ~3.5 ms of the ~11 ms gap; the rest is the
   platform.
2. **Linux's *rationale* does not reproduce, not just its number.** On Linux, 10 ms sits 2.9× above
   the shell hook and 3.2× below a Python one — it discriminates. On this Mac a Python dispatcher
   costs 26 ms against the shell hook's 15, a factor of 1.7, and **no single threshold separates
   them**. So `MAC_LATENCY_BUDGET_S = 0.040` asserts a weaker property than its Linux sibling, on
   purpose and in writing: 2.6× the measured cost, 6× below the 250 ms class of failure the Linux
   probe measured, 125× below the 5 s the settings entry allows (E18). It is a ceiling on what an
   agent can feel, not a discriminator between dispatcher designs.

## Result 5 — `ps -o lstart=` is a working liveness probe, with a coarser token

Added 2026-09-20 (second pass), when the live lane ran on this Mac for the first time and seven
`/proc` reads in `tests/` turned out to be either a `FileNotFoundError` or — worse — a check that
passed without checking, because `Path("/proc/<pid>").exists()` is simply always `False` here.

`MacHost.process_liveness()` was written from D55's prose and had never been executed. It was run
against real pids on this host:

| case | `ps -o lstart= -p <pid>` | `process_liveness(...).alive` |
|---|---|---|
| this process | rc=0, `Sun Sep 20 13:18:59 2026` | `True` |
| a live child (`sh -c 'sleep 30'`) | rc=0, a start string | `True` |
| an **unreaped zombie** (child exited, not waited) | rc=0, a start string | `True` |
| `launchd` (pid 1, owned by root, **not ours**) | rc=0, `Sun Sep 20 08:32:03 2026` | `True` |
| a child that has exited and been reaped | rc=1, empty | `False` |
| an impossible pid (`0x7FFFFFFF`) | rc=1, `ps: process id too large` | `False` |
| this process, with a **mismatched** start token | — | `False` (the pid-reuse guard) |

Cost: **4.1 ms median, 8.8 ms worst** over 20 calls, comfortably inside the 2 s probe timeout.

Two things follow.

1. **The code was right and is now measured.** No behaviour changed; the annotations did. The
   zombie row is worth naming because it matches Linux: `/proc/<pid>` also exists for a zombie, so
   both drivers answer "alive" for a process that has exited and not been reaped. That is the same
   answer, not a platform difference.
2. **The token is coarser here, and that is a real narrowing.** `lstart` is spelled to the second;
   Linux's field 22 is in jiffies. A pid reused *within the same second* would present the same
   token, and the pid-reuse guard would not see the substitution. Recorded rather than smoothed
   over — it is the one place where the macOS driver is weaker than the Linux one.

This is what lets `tests/` ask the seam instead of reading `/proc`, which matters beyond
portability: `os.kill(pid, 0)` is the obvious portable idiom and this repo refuses it by name
(`tests/e2e/conftest.py`, `tests/e2e/test_live_master.py`) because a probe that signals is a probe
that can end something — on 2026-09-17 one rebooted the host. `ps` reads a table.

## What this does not settle

G1 has five items. **Four close here** — the socket budget (§1), the netcat flag set (§2), the
runtime dir (§3) and `ps` liveness (§5) — and Result 4 is a fifth measurement, of the hook's cost
rather than of a constant. One does not, and its `# UNVERIFIED (no capture)` annotations in
`src/shepherd/host/mac.py` are unchanged and still true:

* **`launchctl print gui/<uid>`** — no capture of its output shape exists, so `supervision()`'s
  `manageable=False` and `MAC_SUPERVISION_DETAIL` remain written-not-measured.
* **`LOCAL_PEERCRED` / `LOCAL_PEERPID`** for `peercred()`, which still answers `None`. macOS
  returns an `xucred` carrying no pid in the documented struct, and D41 forbids typing a shape from
  memory. Not a `HostPlatform` member (it is a module function per platform, chosen in
  `host/detect.py`), so it does not block `supervision()` — it is simply still unknown.

`MacHost.verified()` therefore still returns `False`, and the reason is now a single one:
`supervision()` is written from prose. The flag reports on the **driver**, not on any one value, so
one unmeasured member of seven is enough to keep it down — which is the point of having it.

## Reproduce Result 2

`tests/engines/test_hook_dispatch_delivery.py` is this probe, kept as a test: it takes the command
from `detect_host().hook_dispatch(plan)` — never a literal of its own — runs it against a real
listening socket, and asserts byte-identical delivery of both frame sizes plus the bound against a
listener that never reads. It runs on both platforms, so the same property is checked for the Linux
command by the same assertions.<sup>[amended]</sup>

**[amended] 2026-09-20, by the review of this probe's own test.** The paragraph above was true of
the *intent* and false of the *code*, and the difference is the whole point of Result 2. The
sentence "plus the bound against a listener that never reads" did not describe what ran:
`Listener._accept()` held the accepted connection in a local and returned, so the last reference
dropped, CPython closed the fd, and the "never reads" peer in fact **hung up immediately**. The
writer got EOF, not a blocked `write()`. The bound assertion therefore passed in **0.02 s** —
against a command with no outer bound at all, i.e. against exactly the regression it exists to
catch. That is this repo's signature defect class: a timing-bounded assertion whose fixture cannot
produce the slow case.

Fixed by holding the connection for the listener's lifetime. Because a fix alone would only move
the tautology, it is paired with a **negative control**,
`test_the_wedge_fixture_really_wedges_an_unbounded_writer`, which drives the *same*
`Listener(hang=True)` with a stdlib writer carrying no bound at all and requires it to **exceed**
the ceiling. Measured on this host after the fix: the bounded product command **0.27 s**, the
unbounded writer **> 2.0 s** (killed at the ceiling). Before the fix both were 0.02-0.04 s. The two
numbers are now two decades apart, which is what makes the bound assertion a discriminator rather
than a formality. The original sentence is left standing above, marked, rather than rewritten.
