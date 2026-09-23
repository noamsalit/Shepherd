# A suite built on Linux as root, run on macOS for the first time

**Date:** 2026-09-20 · **On `main`:** `1dc1713`, `769cdb3`, `09671c0` (plus `b601a8e`, `e82d86c`)

*Originally branch `fix/macos-port` (`59261db`, `8d068bf`, `499f450`). That branch was rewritten
onto the scrubbed parentless root during publish preparation, so the shas above are the ones that
exist today; the originals resolve only inside `/root/shepherd-branch-archive-20260923.bundle`.*

## Problem

M1–M4 were built, verified and QA'd entirely on one Linux host, running as root.
The first `pytest` on a Mac produced **14 failures and 25 errors** — and, less
visibly, **28 tests that had been passing by not running at all**. The live lane,
run later the same day, produced a further 6 failures and 9 errors.

## What didn't work

**Reading the failure list as a list of bugs.** The obvious grouping was: no
`timeout` binary, a root-only `chown`, socket paths too long. Two of those three
were the same cause, and the loudest symptom pointed at the wrong file.

- The three `test_hookd_command.py` failures looked like a `MacHost` bug. They
  never touch `MacHost` — their helper calls `LinuxHost().hook_dispatch()` and
  does a live `shutil.which("timeout")` against whatever host is running.
- The eight `test_controld.py` failures looked like path length. They were not:
  `MacHost.environ` defaulted to `{}` where `LinuxHost` defaults to
  `dict(os.environ)`, so `detect_host()` returned a driver blind to `HOME` and
  `TMPDIR`. The suite had been writing a real `shepherd.db` into
  `~/Library/Application Support/Shepherd`.

**Passing `--basetemp` to make the red go away.** It cut 62 errors to 25 and hid
the fact that tests were binding sockets under a path the suite should have been
choosing for itself.

## Solution

One product change, `src/shepherd/host/mac.py`:

- `environ` / `uid` defaults now mirror `LinuxHost` exactly.
- `MAC_DISPATCH_REQUIREMENTS` `("timeout","nc")` → `("perl","nc")`; the command
  becomes `perl -MTime::HiRes=alarm -e 'alarm 0.25; exec @ARGV or exit 0' nc -U
  <sock> || true`. Stock macOS has neither `timeout` nor `gtimeout`. The alarm
  survives `execve`, so it bounds `nc` rather than perl's startup. **D55
  re-decided in the open**, per spec §0, and amended in §3.
- `MAC_SOCKET_PATH_BUDGET = 103` was already correct — measured: 103 binds,
  104 raises.
- Liveness constants moved `UNVERIFIED` → `VERIFIED`, closing **G1 item 4**.
  G1 is now 4 of 5; `verified()` stays `False` for `launchctl` alone.

Everything else was test code: `detect_host()` where eight modules had hard-coded
`LinuxHost()`, a `foreign_owned_repo` fixture that skips only when the `chown`
itself is refused, seven `/proc` reads moved to the `HostPlatform` seam, and a
short temp root behind an `lstat` ownership gate with a grace floor and a count
ceiling.

## Why

**Isolation of the name is not isolation of the effect** — the same shape as this
repo's two incident rules. A seam every caller reaches through `detect_host()` is
a seam; a seam half the tests spell `LinuxHost()` is a Linux assumption with a
seam-shaped comment on it.

`nc -U -w 0`, the obvious `-q0` analogue, was rejected **on measurement**: it
truncates a 40 KB frame to ~16 KB, 3/3, at exit 0, while looking correct on small
frames. No string assertion can see that.

`os.kill(pid, 0)` is the obvious liveness idiom and this repo refuses it by name
at `tests/e2e/conftest.py:427` — a probe that signals is a probe that can end
something, and on 2026-09-17 one did, to pid 1. `HostPlatform.process_liveness`
already answered the question on both platforms and sends nothing.

## Prevention

1. **A test that says `LinuxHost()` and means "this host" is a platform bug
   waiting for a platform.** Ask the seam.
2. **Count the skips on a new platform before trusting the pass count.** 28 tests
   self-skipped with `no dispatcher on this host` — the hook lane's entire
   acceptance surface — and the run was green. A silent skip is `unknown` hiding,
   and principle 5 says `unknown` is counted and displayed.
3. **A timing-bounded assertion needs a negative control that drives the same
   fixture with a deliberately unbounded command.** The wedged-peer listener held
   the accepted connection only in a local; `return` closed the fd, so the peer
   hung up in 0.02 s and the bound test passed against a command with **no bound
   at all**. It was the single executable proof behind the D55 re-decision.
4. **Prove a check bites without planting anything executable** (`CLAUDE.md` rule
   2): an out-of-tree autouse plugin on `PYTHONPATH` patching in memory, or a
   TEXT copy of the target parsed as an AST. Both were used; nothing was written
   into the repo.
5. **Generalising a platform constant needs the original literal re-asserted
   alongside it** (`assert LINUX_SOCKET_PATH_BUDGET == 107`), or the test becomes
   a tautology about whatever the host returned.
6. **An isolation fixture that scrubs env var names proves nothing on a platform
   whose driver does not read them.** `test_s8` and `test_s9` scrubbed
   `XDG_DATA_HOME` and asserted the daemon stayed inside the throwaway; `MacHost`
   ignores XDG. Assert the directories the driver actually resolved.
7. **A removed precondition leaves its prose behind.** When a guard is dropped
   because it went red, the comment that introduced it keeps claiming it.
8. **`-q` in `addopts` plus `-q` on the command line is `-qq`**, which suppresses
   the pass/fail summary. `pyproject.toml` already carries one.

## Still open

- **`tests/e2e/` writes to the operator's real data directory.** No environment
  satisfies both subjects: Shepherd needs a throwaway `HOME`, and the engine
  reads its account record from `$CLAUDE_CONFIG_DIR/.claude.json` while the real
  one is at `~/.claude.json`, so a throwaway `HOME` logs the engine out.
  Measured, then reverted — with the redirect, one live failure was fixed and two
  passing tests broke. The fix is to inject a `HostPlatform` at the
  `controld.start` call sites.
- **`pytest` has never run on Linux since this change.** `src/` is one file and
  instantiates only under `darwin`, but `tests/conftest.py`'s `pytest_configure`
  is not platform-gated: on Linux it relocates `--basetemp` and eagerly removes a
  green run's base.
- **Two spawn tests remain red** pending one datum — the untruncated
  `last screen was <KIND>` line from `test_a_spawn_registers_exactly_one_row`.
  No timeout was lengthened to hide them.
