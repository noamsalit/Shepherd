# Shepherd — working rules

## tmux: never use a bare `kill-server`

`tmux kill-server` is global. It terminates the tmux server and **every session
on it**, including this one and any Remote Control sessions the user is driving
from their phone.

On 2026-09-12 the M3 tmux spike opened with `tmux kill-server` as a "clean
slate" step and destroyed three live sessions, including the one that issued it
(exit 137, two seconds later). See §18 "Incident 2026-09-12" in
`docs/specs/orchestrator-platform.md`.

Rules:

1. **Never run `tmux kill-server` without `-L`.** There is no situation in this
   repo where the correct blast radius is "every tmux session on the machine".
2. **Spikes and experiments get a throwaway socket.** `tmux -L shepherd-spike …`
   for every command, teardown included.
3. **`-L` on the session is not enough.** A command run *inside* tmux inherits
   `$TMUX` and resolves to that session's own socket, so a bare `kill-server`
   from within an isolated socket still kills that socket. Pass `-L` explicitly
   on **every** tmux invocation.
4. **Never put `:` in a tmux session name.** tmux reserves it as the
   `session:window` separator: it silently rewrites the name, and `-t name:win`
   then resolves to a *different* session. Use `shepherd_<id>`.

The user's live sessions run on the `shepherd` socket (`tmux -L shepherd ls`).
Leave them alone.

**The socket is the invariant; the session names are not.** They were `aivisor`,
`main` and `spike` until the 2026-09-17 reboot and are `m3` and `master` after
it. Any check written as "`tmux -L shepherd ls` shows exactly <three names>" is
a check that goes red the next time the user opens a terminal — assert on the
**socket** (never named in a write, refused by `check_tmux_argv` at construction
and again at the exec site), and read the session list only to confirm it is
unchanged *across your own run*.

## Mutations: plant inert fixtures, never live source the suite executes

On 2026-09-17 a verification planted `os.kill(1, signal.SIGINT)` into
`interrupt()` in a **shadow tree** — `scratchpad/m3-remfix/shadow/src/…/runner/local.py` —
to prove P-M3-7's lint catches it. The lint does catch it, statically. But the
suite **imports and executes** that module, `interrupt()` ran before the lint
test was reached, and `SIGINT` to pid 1 is `Ctrl+Alt+Del`: systemd rebooted the
host. 66 days of uptime and three live Remote Control sessions were lost.

**The reasoning error, stated plainly, because it is the reusable part.** The
rule in force was *"never plant in a path whose default target is a real user
file"* — a rule about **where bytes are written**. A shadow tree contains file
writes and nothing else. A planted mutation is **code that runs**, and any
effect that leaves the process — a signal, a subprocess, a socket, a reboot — is
not contained by a directory. This is the same shape as the `tmux kill-server`
rule above: `-L` on the session is not enough because a command *inside* tmux
resolves to its own socket. Isolation of the *name* is not isolation of the
*effect*.

Rules:

1. **A planted violation is an inert fixture that nothing imports.** It lives in
   `tests/boundaries/fixtures/`, it is read as text or parsed as an AST, and it
   is never on an import path the suite executes. `runner_signals_init.py` and
   `runner_kill_server_prefix.py` are the two worked examples.
2. **A shadow tree is not a sandbox.** It isolates the files. It does not
   isolate signals, subprocesses, sockets, ports, or the host. Before planting
   anything into code that will run, ask what escapes the process — and if
   anything does, freeze it as a fixture instead.
3. **Never plant a signal, a `kill`, a reboot-capable call, or a teardown verb
   into executable code at all** — not in the repo, not in a shadow, not in a
   scratch copy. Those are proved by fixture and by predicate, never by
   execution.
4. **Clear `__pycache__` before every mutation run.** CPython decides a `.pyc`
   is fresh from `(source mtime in whole seconds, source size)`. A mutation that
   **preserves file size** and lands **within the same second** as the last
   compile re-imports the *unmutated* bytecode, and the row is recorded as a
   **false survivor** — a hole in the tree written down as a proof that there
   isn't one. M4's T6 caught this on the one size-preserving row in its ledger
   (a single digit changed); applied alone it was red. It is also the most
   likely explanation for T19's unexplained transient, where a test failed
   naming a word that was not in the file on disk.
   Seven of M4's nine drivers did not clear the cache. **Recorded REDs are
   unaffected** — a red proves the mutation took effect — so the exposure is to
   *survivors*, and every unintended survivor this milestone recorded was
   investigated and closed as a real test gap. The rule exists so the next one
   does not have to be.
5. **The runtime net exists and is not a substitute for the rules above.**
   `tests/conftest.py` makes `os.kill`/`os.killpg` refuse pids `0`, `1` and `-1`,
   and `tests/test_signal_guard.py` proves the net itself bites using signal `0`,
   which delivers nothing. A guard against a reboot must not be able to cause
   one.

## `docs/probes/` is frozen evidence — and what it took to unfreeze it

The probe corpora are **read-only**. A capture edited to look tidy stops being
evidence: its whole value is that it is what a command actually printed, and a
reader cannot tell a helpful edit from a wrong one after the fact.

On **2026-09-20** that rule was overridden, once, deliberately, and at the
owner's explicit instruction: a former employer's project prefix appeared in a
probe's throwaway branch name, and it had to leave the repository. The override
is recorded rather than quiet, and it came with three conditions that are the
standing terms for any future one:

1. **The owner asks for it.** Not a tidy-up, not a judgement call made while
   doing something else.
2. **Every touched file says so, in itself.** Each carries a notice naming the
   single token that was substituted and stating that nothing else changed. A
   sanitised capture that does not admit it is a fabricated one.
3. **The generator is changed with the capture.** `probe_git.sh` was renamed
   alongside `captures/git.txt`, so re-running the probe reproduces the file as
   written. The property that made the corpus worth freezing is that it is
   *regenerable*; an edit that breaks that is not available even with an
   instruction.
