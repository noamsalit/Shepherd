# Probe — `hookd` dispatcher latency and delivery (2026-09-16)

**Question.** §8 of the spec sketches `hookd.py` — a Python dispatcher that reads the hook
payload on stdin, writes it to `sessiond`'s UDS with a 250 ms timeout, and always exits 0.
`implementation-constraints.md` C7 and `data-schemas.md` §StopFailure / §"Hook runtime contract"
record a problem with that shape: **a Python hook running at `-p` shutdown was killed and its
payload lost, 2 times out of 2**, while a fork-free bash hook on the same events survived
(`docs/probes/2026-09-14-schemas/hooks/live/S07_bad_model/debug-hooklines.txt`,
`…/R04_settings_flag/debug-hooklines.txt`). The cause is inferred there, not observed: the
suspicion is interpreter start-up, not the socket timeout.

This probe measures the cost directly, so M1 picks the dispatcher on numbers instead of on the
inference.

**Host.** Linux 6.8, Python 3.12.3, OpenBSD netcat 1.226-1ubuntu2, `/run/user/0` tmpfs.
**Evidence.** `/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/hookd-probe/`
(scratch; the scripts are reproduced below, which is what makes this re-runnable).
**Status:** verified live 2026-09-16. Not yet verified on macOS — see "What this does not settle".

---

## Result 1 — cost per hook invocation

25 invocations each, one real `PreToolUse` payload (257 bytes, copied from
`data-schemas.md` §"Common input fields"), measured end to end from `sh -c` exec to exit.
The listener is a Python UDS server that reads to EOF.

| Dispatcher | ms per call | vs Python |
|---|---|---|
| `python3 hookd.py` (the spec's shape) | **31.7** | 1.0× |
| `python3 -S -E hookd.py` (no `site`, no env inspection) | 27.2 | 1.2× cheaper |
| `sh` + `nc -U` | **3.4** | **9.3× cheaper** |
| `sh` + append to a spool file | 2.9 | 10.9× cheaper |

Stripping `site` buys 14%. It does not change the class: the interpreter itself is the cost,
and both Python variants sit an order of magnitude above a shell hook.

## Result 1b — `-q0` is load-bearing, and dropping it fails silently

Added 2026-09-16 after a plan review caught a draft dispatcher that had lost the flag. Same
listener, same payload, 10 invocations each — the only difference is `-q0`:

| Command | ms per call |
|---|---|
| `timeout 0.25 nc -U -q0 "$1"` | **3.2** |
| `timeout 0.25 nc -U "$1"` | **253.6** |

**79× worse, and 8× worse than the Python dispatcher this whole decision exists to avoid.**

The mechanism: without `-q0`, `nc` does not shut down its write side when stdin reaches EOF. A
listener that reads to EOF therefore never sees the frame end, neither side closes, and the call
blocks until `timeout 0.25` kills it. The cost is not a slow path — it is *every* invocation of
*every* event of *every* session, paid at 250 ms, on the synchronous `MessageDisplay` hook among
others.

**The part that makes this dangerous rather than merely wrong: it still delivers.** Both variants
landed all 20 frames. There is no error, no dropped payload, and no failing assertion — just a
quarter-second added to every hook, which would read as "Claude Code feels sluggish since we
installed Shepherd" and never point at the flag.

Two consequences worth carrying: the dispatch command must have **exactly one definition site**
(a divergent copy in a second document is what produced the near-miss), and since `-q0` is
precisely the flag that is not portable to macOS's netcat, this measurement is also the argument
for the command being a `HostPlatform` value rather than a constant.

## Result 2 — delivery is intact, not merely fast

`sh` + `nc -U` against a listener that records frame sizes:

```text
FRAME bytes=77    head={"session_id":"s1","hook_event_name":"Stop","las
FRAME bytes=77    head={"session_id":"s1","hook_event_name":"Stop","las
FRAME bytes=77    head={"session_id":"s1","hook_event_name":"Stop","las
FRAME bytes=40011 head={"pad":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Three small frames and one 40 KB frame arrive byte-complete. 40 KB is far above the largest real
payload in the corpus, so payload size is not a reason to prefer an in-process client.

## Result 3 — the daemon-down path (principle 4)

With no listener bound at the target path:

```text
sh+nc, socket absent: 3.6 ms/call
exit code with no daemon: 0
```

A dead `sessiond` costs the agent 3.6 ms and returns exit 0. That is principle 4 — "a dead daemon
degrades visibility, never agents" — satisfied by measurement rather than by assertion.

---

## What this means for M1

1. **The dispatcher should not be a Python process.** At 31.7 ms it is ~9× the shell cost on
   every event, it is the exact shape that lost `StopFailure` 2/2 at shutdown, and
   `MessageDisplay` is dispatched with `forceSyncExecution` (data-schemas §MessageDisplay), so the
   cost lands on the user's screen latency. The §8 code block is illustrative, not a numbered
   decision, so choosing a shell dispatcher reverses nothing — but it should be written down as a
   deliberate choice, which is what this file is for.
2. **§18's write-volume risk shrinks by the same factor.** "`PostToolUse` × 20 concurrent
   sessions" is a different question at 3.4 ms than at 31.7 ms.
3. **The 250 ms socket timeout stays.** It bounds a hung `sessiond`; it never bounded interpreter
   start-up, which is what actually bit.
4. **The fallback path is worth keeping in view.** A spool-file append (2.9 ms) needs no daemon
   listening at hook time at all, which removes the shutdown race entirely at the cost of a tail
   reader. The socket remains the primary path; this is the degrade to reach for if the race
   survives the change.

## What this does not settle

- **macOS (D55).** `nc -U` exists on macOS, but the flag set differs — `-q0` is not portable, and
  macOS's netcat is a different build. The hook command line is therefore a `HostPlatform`
  concern, not a constant. **Gap: no macOS capture exists for any of this.**
- **`nc` is a host dependency.** It is present here; it is not guaranteed on a minimal container
  image. The installer must check for it and say so, rather than writing a hook that silently
  does nothing.
- The kill-at-shutdown cause remains inferred. This probe shows the Python hook is ~9× more
  expensive; it does not prove that expense is *why* it was killed. The change is justified by
  cost and by the observed loss together, not by a proven mechanism.

## Re-run

```sh
# listener
python3 listener2.py /run/user/0/shp-probe2.sock frames.txt &

# the two candidate hooks
cat > sh_hook_nc.sh <<'SH'
#!/bin/sh
exec 2>/dev/null
timeout 0.25 nc -U -q0 "$1" || true
exit 0
SH

cat > py_hook.py <<'PY'
import sys, socket
try:
    payload = sys.stdin.buffer.read()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.25); s.connect(sys.argv[1]); s.sendall(payload); s.close()
except BaseException:
    pass
sys.exit(0)
PY
```

Then time 25 invocations of each against the same payload.
