# Setup Record: Shepherd-local

**Environment key:** `Shepherd-local` · **Mode:** local
**Target repo:** `/root/Shepherd` · **First created:** 2026-09-22T21:39:30Z · **Last updated:** 2026-09-22T21:39:30Z (wf:wf-20260921T212808Z-9172ed6b)

> **This file records only what was MEASURED. If preflight did not observe it, it does not go in.**
>
> That is the whole discipline, and it is what makes this file different from `env-plan.md`.
> The env plan is a *prediction* written by reading source code — necessary, and systematically
> wrong about environments, because environment facts are not in the code. This file is the
> other half: what the machine actually said when someone asked it.
>
> A prediction that leaks in here turns a record you can trust into a second env-plan, and then
> there are two places for the same fact to go stale. **No section of this file may be filled in
> before a run.** If a heading could be answered from a document, it does not belong here.

**Append-only.** Nothing is ever overwritten or deleted. A fact that stops being true is marked
`superseded` and the new observation is appended beneath it.

**Scope: the environment, not the feature.** Keyed by `Shepherd-local`, machine-local, gitignored.

---

## 1. Identity

| Field | Value |
| ------- | ------- |
| `env_key` | `Shepherd-local` |
| Environment mode | `local` |
| Target repo + branch | `/root/Shepherd` @ `integration` |
| Host OS / arch | `Linux x86_64` (`uname -sm`) |
| First created | 2026-09-22T21:39:30Z · wf:wf-20260921T212808Z-9172ed6b |
| Last updated | 2026-09-22T21:39:30Z · wf:wf-20260921T212808Z-9172ed6b |
| Workflows that have written here | wf:wf-20260921T212808Z-9172ed6b |

---

## 2. Measured facts

One row per fact. **A row missing `How observed` or `Observed output` is invalid and must be
deleted rather than guessed at.**

| Fact | Volatility | How observed | Observed output | First observed | Last confirmed | Fingerprint | State |
| ------ | ------------ | -------------- | ----------------- | ---------------- | ---------------- | ------------- | ------- |
| branch currency — Shepherd | volatile | `git rev-parse --abbrev-ref HEAD; git rev-parse --short HEAD; git rev-list --count HEAD..main; git status --porcelain` | branch `integration`; sha `c243773`; `HEAD..main` = 2; `main..HEAD` = 108; dirty = yes (9 entries, all `.cc10x/`, `.claude/`, `docs/methodology/`) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `main` and `integration` have **no common ancestor** | derived | `git merge-base HEAD main` → exit 1; `git rev-list --max-parents=0 HEAD` vs `… main` | merge-base exit 1; roots `8685558` (integration) vs `22d9ef2` (main) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | roots `8685558`/`22d9ef2` | current |
| `integration` has no upstream | stable | `git rev-parse --abbrev-ref --symbolic-full-name '@{u}'` | `fatal: no upstream configured for branch 'integration'` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `docs/probes/` clean (frozen evidence) | volatile | `git status --porcelain docs/probes/` | (empty) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `src/` and `tools/` clean | volatile | `git status --porcelain src/ tools/` | (empty) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| venv python | stable | `test -x /root/Shepherd/.venv/bin/python && .venv/bin/python -V` | `Python 3.12.3` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| store migrations 001–004 present | stable | `ls -1 src/shepherd/store/migrations/` | `001_m1_foundation.sql 002_m2_stop_verdicts.sql 003_m3_mailbox.sql 004_projects.sql` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| git | stable | `git --version` | `git version 2.43.0` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| tmux | stable | `tmux -V` (the one argv legal without `-L`; contacts no server) | `tmux 3.4` at `/usr/bin/tmux` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| **`$TMUX` is INHERITED and non-empty** | volatile | `echo "TMUX=${TMUX:-<unset>}"` | non-empty; names a socket that is **not** `shepherd-qa` (value deliberately not transcribed — that socket is never to be written to or enumerated) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| playwright importable | stable | `.venv/bin/python -c "import playwright"`; `importlib.metadata.version` | `1.63.0` at `/root/Shepherd/.venv/lib/python3.12/site-packages/playwright/` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| playwright **undeclared** in `pyproject.toml` | derived | `grep -n -i playwright pyproject.toml` | no match (exit 1); `dependencies = ["claude-agent-sdk>=0.2.153,<0.3", "anyio>=4.15"]` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `dependencies` list as quoted | current |
| chromium binary | stable | `p.chromium.executable_path`; then `<path> --version` | `/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome` → `Google Chrome for Testing 153.0.8010.12` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| chromium **launches** (real `launch()`+`close()`) | volatile | `.venv/bin/python -c "…chromium.launch(headless=True); new_page(); set_content; evaluate('document.readyState'); close()"` | `readyState = complete`; `probe text = ok`; `LAUNCH+CLOSE OK in 0.63s`; exit 0 | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| **chromium is NOT resolvable under env-plan §7's redirected env** | derived | `env -u PLAYWRIGHT_BROWSERS_PATH HOME=$S/home XDG_CACHE_HOME=$S/xdg_cache .venv/bin/python -c "…p.chromium.executable_path…os.path.exists(ep)"` | resolved `$S/xdg_cache/ms-playwright/chromium-1243/chrome-linux64/chrome`; `exists = False` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | env-plan §7 row `PLAYWRIGHT_BROWSERS_PATH` = "inherited … not overridden" | current |
| `PLAYWRIGHT_BROWSERS_PATH` is **unset** on this host | volatile | `echo "PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH:-<unset>}"` | `<unset>` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| the fix: explicit `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` restores launch under redirect | derived | same redirected env **plus** `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright`, full `launch()`/`new_page()`/`inner_text`/`close()` | `resolved = /root/.cache/ms-playwright/…/chrome`; `inner_text = ok`; `LAUNCH UNDER REDIRECTED ENV: OK`; exit 0 | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | chromium-1243 under `/root/.cache/ms-playwright` | current |
| Linux AF_UNIX budget is **107 bytes** (108 refuses) | derived | real `socket.AF_UNIX` bind at exactly 107 and exactly 108 bytes in a `/tmp` tempdir | `107 bytes -> BOUND`; `108 bytes -> REFUSED: AF_UNIX path too long` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `LINUX_SOCKET_PATH_BUDGET = 107` (`host/linux.py:42`) | current |
| socket-path arithmetic (product's own `plan_socket`) | derived | `.venv/bin/python` importing `plan_socket`, `APP_DIR_NAME`, `CONTROL_SOCKET_NAME`, `LINUX_SOCKET_PATH_BUDGET` and evaluating four candidate `XDG_RUNTIME_DIR` values | fixed suffix `/shepherd/controld.sock` = **23 bytes**; max `XDG_RUNTIME_DIR` = **84 bytes**. `$SCRATCH` (76) → 99, **ACCEPTED margin +8**; `$SCRATCH/xdg_runtime` (88) → 111, **REFUSED by 4**; `/tmp/shq5-<7-digit pid>` (17) → 40, **ACCEPTED margin +67**; `/run/user/0` (11) → 34, ACCEPTED margin +73 | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `plan_socket` at `host/base.py:147-167` | current |
| session scratchpad path length | stable | `echo -n "$SCRATCH" \| wc -c` | **76** bytes (`/tmp/claude-0/-root-Shepherd/<uuid>/scratchpad`) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| **the session scratchpad holds a REGISTERED git worktree of the repo under test** | derived | `git worktree list`; `cat /root/Shepherd/.git/worktrees/macwt/gitdir` | `$SCRATCH/macwt  dade568 (detached HEAD)`; registry entry `/root/Shepherd/.git/worktrees/macwt/gitdir` → `$SCRATCH/macwt/.git` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | worktree name `macwt` | current |
| the session scratchpad is long-lived and shared | volatile | `ls -1 $SCRATCH` | ~250 pre-existing entries from prior milestone work (`m4-t19`, `shots-*`, `mut*`, `qa`…`qa4`, `macwt`, …) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `XDG_RUNTIME_DIR` on this host | volatile | `echo "$XDG_RUNTIME_DIR"; test -d` | `/run/user/0`, exists | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| no stale `/tmp/shq5-*` from a prior run | volatile | `ls -d /tmp/shq5-* 2>/dev/null` | none | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `/tmp` writable, disk headroom | volatile | `test -w /tmp`; `df -BM --output=avail /tmp`; `df -i /tmp` | WRITABLE; **24622 MiB** avail; 2232225 free inodes (10% used) | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| screenshot footprint, measured not estimated | derived | real chromium screenshots at the plan's nine widths (320…2560), `os.path.getsize` each | one 9-width sweep = **224826 bytes (220 KiB)**; S23+S24 ≈ 50 loads ≈ **1.2 MiB**; a generous 400 shots ≈ **9.5 MiB** — i.e. ~2600× headroom | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | width set `[320,390,760,761,820,900,1280,1920,2560]` | current |
| loopback bindable on an ephemeral port | volatile | `socket.socket(); bind(('127.0.0.1',0)); getsockname(); close()` | `bound 127.0.0.1:60169`; `closed` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `probe_repo` subprocess path works on all three fixture shapes | derived | `.venv/bin/python` importing `shepherd.signals.binding.probe_repo`, against a real `git init` repo, a plain dir, and a regular file, all created under the scratchpad | R1 real repo → `GitProbe(git_common_dir=…/.git, failure=None)`; R2 non-git dir → `GIT_NOT_A_REPO`, detail `fatal: not a git repository…`; R3 regular file → `GIT_NOT_A_REPO`, detail `[Errno 20] Not a directory` — **handled, not raised** | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `binding.py:167-169` | current |
| the scratchpad is outside any git repo, so the `add_repo` refusal path is genuine | derived | the R2 probe above returned `not a git repository (or any of the parent directories)` | as quoted — no parent `.git` is found by walking up from `/tmp/claude-0/…` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | scratchpad under `/tmp`, not under `/root/Shepherd` | current |
| a 12-level nested repo path is creatable for P3 | volatile | `mkdir -p $S/repo/lvl00/…/lvl11 && git init -q && git commit --allow-empty` | created; path length 156 bytes | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| `runner_socket` is read from the store **at compose time** | derived | read `toolsurface/compose.py:261-268` (`runner_socket`) and `:285` (`build_runner`) — **not exercised** | `store.get_app_state("runner_socket")`, falling back to `DEFAULT_SOCKET`; `build_runner` calls it once and hands `permitted_sockets(socket)` to the exec site | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `compose.py:261`, `compose.py:285` | current |
| pytest default collection | volatile | `.venv/bin/python -m pytest --collect-only` | **2226/2302 collected, 76 deselected** in 2.17s, exit 0 | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | — | current |
| the `live` deselection is **exact** | derived | `pytest --collect-only -q -m live`, summing the per-file counts | 15 files, `10+14+1+7+6+3+7+1+5+1+1+1+7+11+1` = **76** — identical to the 76 deselected by default `addopts = -m 'not live'` | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `addopts = "-q -m 'not live'"` | current |
| three `tests/e2e/` node ids ARE collected by default, deliberately | derived | `pytest --collect-only -q \| grep "^tests/e2e/"`; then read the modules | `test_live_lane_typechecks.py: 2` (module docstring: *"carries no `pytest.mark.live`, and that is the whole point"*; runs `mypy`/`pytest` subprocesses only) and `test_live_master_isolation.py: 1` (`test_the_recorded_p4_finding_…`, no fixture). Neither starts a `claude` process | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | those two module paths | current |
| the node-id freeze is a **subset** check (C-8 premise) | derived | `grep` of `tests/boundaries/test_collected_node_ids.py` | `subset_violations(baseline_node_ids(), live, RETIRED_NODE_IDS) == []` at `:309`; `RETIRED_NODE_IDS` at `:37` — adding round-5 files is safe, renaming needs an entry | wf:…9172ed6b | wf:…9172ed6b @ 2026-09-22T21:39:30Z | `test_collected_node_ids.py:309` | current |

### What each volatility class means, and what preflight does with it

| Class | Meaning | Preflight behaviour on run 2+ |
| ------- | --------- | ------------------------------- |
| `stable` | changes only when a human changes the machine | re-run the **cheap existence probe only**, and compare against `Observed output` |
| `volatile` | true only for an instant | **always re-checked, never trusted from this file** |
| `derived` | a fact learned the hard way about the product or topology | **never re-checked mechanically**; carried forward as a constraint, guarded by `Fingerprint` |

### State transitions

| From | Trigger | To | Consequence |
| ------ | --------- | ---- | ------------- |
| `current` (`stable`) | the cheap re-probe disagrees with `Observed output` | `superseded` | append the new observation as a new row; preflight reports `SETUP_RECORD_STALE: true` |
| `current` (`derived`) | `Fingerprint` no longer matches | `unverified` | **not** `superseded` — the harness must treat that fact as a *prediction* again |
| `unverified` | re-observed | `current` | new row appended with a fresh fingerprint |

---

## 3. Human prerequisites, measured

Only items preflight **confirmed missing or present**.

| Item | Why it is needed | How to acquire | Supplied? | Where it lives | Class |
| ------ | ------------------ | ---------------- | ----------- | ---------------- | ------- |
| — | — | — | — | — | — |

**None. The env plan's §3 claim of zero `human`-owned blockers is CONFIRMED by measurement, not
repeated on trust.** Every prerequisite it names was probed and found present on this host: `git`
2.43.0, `tmux` 3.4, `.venv` Python 3.12.3, playwright 1.63.0 with a chromium-1243 that really
launches, a writable `/tmp` with 24 GiB free, a bindable loopback, four migrations on disk, and a
clean `docs/probes/` / `src/` / `tools/`. Nothing here requires a person.

---

## 4. Corrections to `env-plan.md`

| What `env-plan.md` predicted | What was measured | Which env-plan section now disagrees | Routed? | Class |
| ------------------------------ | ------------------- | -------------------------------------- | --------- | ------- |
| `PLAYWRIGHT_BROWSERS_PATH` — "inherited; chromium-1243 already resolved in `.venv`; not overridden" | It is **unset**, and chromium does not live in `.venv` — it lives at `/root/.cache/ms-playwright/chromium-1243/`, a path derived from `XDG_CACHE_HOME`/`HOME`, **both of which §7 redirects into the scratchpad**. Under §7's own environment, `executable_path` resolves to a non-existent file (`exists = False`) and bring-up step 9 would fail after ~45 s of bring-up, looking like a chromium fault. Setting `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` explicitly was measured to fix it | §7 (`PLAYWRIGHT_BROWSERS_PATH` row); §3 (the T2 prerequisite, which passes under the real env and fails under the harness env — a preflight that cannot catch its own harness); §4 step 9 | yes — report | `wrong-guess` |
| §2 "Flags that must be OFF" lists "any inherited `$TMUX`" | `$TMUX` **is** inherited and non-empty on this host — so the mitigation is live, not hypothetical. But **`TMUX` does not appear in §7's table**, and §7 is the section this plan says maps mechanically to the manifest's `required_env`/`environment` (9 rows, all `XDG_*`/`HOME`/`TMPDIR`/`CLAUDE_CONFIG_DIR`/`PLAYWRIGHT_BROWSERS_PATH`). A manifest generated mechanically from §7 would not unset it | §7 (missing `TMUX` row); §2 states the rule in a section that is not translated | yes — report | `wrong-guess` |
| §9 step 8: teardown is `rm -rf $SCRATCH`, and §5 calls the scratchpad fresh per run ("Each run creates a new scratchpad … and destroys all four") | `$SCRATCH` is a **long-lived, shared session directory** holding ~250 prior artifacts **and a registered git worktree of the repo under test** (`$SCRATCH/macwt`, registry entry `/root/Shepherd/.git/worktrees/macwt/gitdir`). `rm -rf $SCRATCH` would delete that worktree and leave a corrupt registry entry — and §9 step 9's verification (`git status --porcelain src/ tools/ docs/probes/`) would still report **empty**, i.e. a teardown that breaks the repo and verifies clean | §9 steps 8–9; §5 "Reset between runs"; §10 | yes — report | `wrong-guess` |
| B9 / §2 / §7: "the scratchpad path alone is ~88 [bytes]", therefore `XDG_RUNTIME_DIR` inside it is refused | The scratchpad root is **76** bytes. 88 is the length of `$SCRATCH/xdg_runtime`, i.e. the *subdir* form. The arithmetic, via the product's own `plan_socket`: suffix `/shepherd/controld.sock` = 23, so the ceiling is 84. Root → 99, **accepted, margin +8**; `xdg_runtime` subdir → 111, **refused by 4**. B9's **conclusion is sound for the form the plan actually intends**, and `/tmp/shq5-<pid>` has 67 bytes of margin — but its stated premise describes a different path than its prose | §11 B9; §2 "Flags that must be OFF"; §4 step 2; §7 `XDG_RUNTIME_DIR` row | yes — report | `wrong-guess` |
| §2 Verification: the `live` gate is `pytest --collect-only -q` asserting the collected set "contains no node id from `tests/e2e/` or `tests/web/test_render_live.py::…` that carries the marker" | Path-based reading is wrong: **3 `tests/e2e/` node ids are collected by default, deliberately** (`test_live_lane_typechecks.py`'s docstring: *"This module carries no `pytest.mark.live`, and that is the whole point"*). The marker-based reading is exactly right and provable as an integer: live-marked = **76** = deselected = **76**. A harness that implements the path reading goes red on three intentional tests | §2 Verification, `live` deselected row | yes — report | `wrong-guess` |

---

## 5. Superseded rows

| Fact | Was | Became | When | Detected by |
| ------ | ----- | -------- | ------ | ------------- |
| — (first run for this `env_key`; nothing to supersede) | | | | |

---

## 6. What this record does NOT contain

- Anything preflight did not run. Preflight stopped at **T4** and booted no service. `controld` was
  never started, no tmux session was created, and the `claude` engine was never spawned. Chromium
  was launched **only** as a launchability probe and closed in the same statement.
- Any fact about the `shepherd` tmux socket. It was never named in a write, never passed to a
  command, and never enumerated — not even to confirm it unchanged.
- Anything about the feature under test. That is `feature-map.md`.
- Any recommendation, plan, or intended state. That is `env-plan.md`.

---

## 7. Appended by `qa-build` — 2026-09-22 (wf:wf-20260921T212808Z-9172ed6b)

**Append-only.** Nothing above was overwritten. Every row below was observed by
running the harness on this machine, not by reading a document.

### 7a. The three `harness decision` blockers — which form was implemented

The env plan's §11 owner census names three `harness decision` rows and requires
the builder to state, here, which behaviour it chose. All three are implemented
in `tests/qa5/`.

| # | Decision | Form implemented | Where it lives | How it was observed | Observed output |
| --- | ---------- | ------------------ | ---------------- | --------------------- | ----------------- |
| **B9** | where `XDG_RUNTIME_DIR` points | **`/tmp/shq5-<pid>`**, minted per run and removed at teardown. The budget is **not** re-derived: `runroot.assert_socket_budget` calls the product's own `plan_socket` with `APP_DIR_NAME`, `CONTROL_SOCKET_NAME`, `SOCKET_DIR_MODE`, `SOCKET_MODE` and `LINUX_SOCKET_PATH_BUDGET`, so a change to either constant moves the check with it | `tests/qa5/runroot.py::assert_socket_budget`, called at bring-up step 2 | the run report's `measurements.socket_bytes_spent`, written by every run | `40` bytes spent against the product's 107-byte budget (`/tmp/shq5-1933702/shepherd/controld.sock`) |
| **B10** | one composition per process | **One `controld` per pytest process, scenarios serial, no `pytest-xdist` in this package.** The whole of `tests/qa5/` is therefore **one manifest scenario command**, not one per wave: splitting the waves across processes would both re-run bring-up per wave and lose the binding S0 measures, which wave 3 consumes out of the session fixture | `tests/qa5/conftest.py::harness` (session-scoped), and the manifest's single `pytest tests/qa5/` scenario | 38 tests in one process, one `controld.start`/`controld.stop` pair per run | `38 passed`, one bind and one shutdown per run |
| **B20** | what teardown removes | **The run-root form.** `$SCRATCH = $SESSION_SCRATCH/qa5-<pid>` is minted at bring-up and is the *only* directory removed, alongside `/tmp/shq5-<pid>`. `$SESSION_SCRATCH` is never removed. The sweep matches `qa5-<digits>` and `shq5-<digits>` **only**, refuses to remove a survivor whose pid is alive, and returns what it removed | `tests/qa5/runroot.py::mint`, `sweep`, `destroy` | teardown's own verification lines, in every run report's `teardown` array | `run root removed: …/qa5-1933702`; `session scratchpad intact: …/scratchpad`; `git worktree list identical to the bring-up baseline` |

### 7b. Facts the build measured that preflight had no way to reach

| Fact | Volatility | How observed | Observed output | First observed | Last confirmed | Fingerprint | State |
| ------ | ------------ | -------------- | ----------------- | ---------------- | ---------------- | ------------- | ------- |
| a full bring-up on this host works end to end | volatile | `.venv/bin/python -m pytest tests/qa5/test_smoke_bringup.py -q` | `1 passed`; `port != 0`, four panes listed on `shepherd-qa`, `/api/fleet` 200, eight workspaces, both SSE clients 200, audit sink non-empty after the seed | qa-build | qa-build @ 2026-09-22 | — | current |
| teardown leaves **nothing** behind | volatile | after a full run: `ls -d /tmp/shq5-*`; `tmux -L shepherd-qa list-sessions`; `git status --porcelain src/ tools/ docs/probes/` | no `/tmp/shq5-*`; `no server running on /tmp/tmux-0/shepherd-qa`; empty status | qa-build | qa-build @ 2026-09-22 | — | current |
| **`sse.py`'s keep-alive cadence is longer than a naive socket timeout** | derived | a raw SSE reader with `timeout=10` went silent at seq 31 during a browser-driving wave; `IDLE_TIMEOUT_S = 15.0` (`web/sse.py:33`) | the rig's own §3a control caught it: client A stopped receiving while client B continued. A reader that dies makes every later "zero frames" assertion pass on a dead socket | qa-build | qa-build @ 2026-09-22 | `IDLE_TIMEOUT_S = 15.0` | current |
| **a blocking `recv` is not woken by closing the `HTTPConnection`**, and `conn.sock` is `None` by then | derived | teardown's join timed out at 15 s twice; `HTTPResponse.will_close` is true for a stream with no `Content-Length`, so `getresponse()` hands the socket to `response.fp` and sets `HTTPConnection.sock = None` | the reader joins only when `shutdown(SHUT_RDWR)` is called on a socket handle captured **before** `getresponse()` | qa-build | qa-build @ 2026-09-22 | `http.client` on CPython 3.12.3 | current |
| **`os.kill(pid, 0)` is available for a liveness probe, and `tests/conftest.py`'s net refuses 0/1/-1** | derived | the sweep probes only pids it parsed out of its own directory names and raises on `pid <= 1` before calling | no probe of pid 0, 1 or -1 was ever issued by this harness | qa-build | qa-build @ 2026-09-22 | `tests/conftest.py` signal guard | current |
| **R1 must not be one of P1's two repos** | derived | seeding R1 into P1 made S32's "add R1's path" a duplicate that `add_repo` refuses, and the draft list never grew | the seed now builds `repo/p1-first` and `repo/p1-second` for P1 and leaves `repo/plain` (R1) free | qa-build | qa-build @ 2026-09-22 | env-plan §5 rows P1 and R1 | current |

### 7c. Corrections this build measured against `env-plan.md`

| What `env-plan.md` predicted | What was measured | Which section now disagrees | Routed? | Class |
| ------------------------------ | ------------------- | ---------------------------- | --------- | ------- |
| §9 step 4's branch assertion checks "both socket paths no longer exist" | `Controld` carries **one** socket path (`control_socket_path`); the ingest path is planned inside `controld.start` and is not returned. Teardown asserts the one it can reach, and says so | §9 step 4 | yes — report | `wrong-guess` |
| §3a's counted window "opens on the `project.deleted` frame of the *previous* control" | Exact only while **every** scenario runs a control. Cell (ii) scenarios deliberately run none, so S4's six legitimate frames sit inside S5's literal window and S5's asserted zero is unreachable. Each cell-(iii) scenario opens its own window and the **control still closes it**, which is the endpoint that makes a zero mean anything | test plan §3a | yes — report | `wrong-guess` |

---

### 7d. Measured after the final fixes (same workflow, same machine)

| Fact | Volatility | How observed | Observed output | First observed | Last confirmed | Fingerprint | State |
| ------ | ------------ | -------------- | ----------------- | ---------------- | ---------------- | ------------- | ------- |
| **a full 35-scenario run costs ~95 s on this host, not 11-16 min** | volatile | `started_at`/`finished_at` in two consecutive run reports | `00:11:31 -> 00:13:04` and `00:13:05 -> 00:14:38` — 93 s each, for 37 recorded scenarios including all 17 `ui` ones | qa-build | qa-build @ 2026-09-23 | — | current |
| **leaking a browser context per scenario cost an order of magnitude** | derived | the same suite, before and after an autouse per-scenario context close | ~13 min with ~30 contexts left open to teardown; **95 s** once each scenario returns its own. The leak also made a 10 s bounded wait expire on a healthy page | qa-build | qa-build @ 2026-09-23 | `tests/qa5/conftest.py::_close_this_scenarios_contexts` | current |
| **the Projects page starts two unawaited `loadDetail` reads and the later one to resolve wins** | derived | S33 failed 1 run in 4 at `#p-paths .path` == 2; `projects.js:250-254` calls `loadDetail(id)` without awaiting and then `renderList()`, while `submitProject`'s create branch has its own `loadDetail` in flight | with a `networkidle` settle before `#proj-edit`, **6/6** consecutive full-suite runs clean; without it, 1 failure in 6. `networkidle` is sound on this page because §12 forbids polling and the product runs no timers | qa-build | qa-build @ 2026-09-23 | `projects.js:250-254` | current |
| full-suite collection grew by exactly the harness, and the `live` gate is unmoved | volatile | `pytest --collect-only -q -o addopts="-m 'not live'"`, then `-m live` | `2264/2340 collected (76 deselected)`, up from `2226/2302 (76 deselected)` — **+38, the 38 tests in `tests/qa5/`** — and **live-marked 76 == deselected 76**, unchanged | qa-build | qa-build @ 2026-09-23 | `addopts = "-q -m 'not live'"` | current |
| the clause-16 node-id freeze is unaffected by adding a package | volatile | `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` | `7 passed` — the freeze is a **subset** check, so adding files is safe and no `RETIRED_NODE_IDS` entry was needed | qa-build | qa-build @ 2026-09-23 | `test_collected_node_ids.py:309` | current |
| **28 of the 31 tests in `tests/web/test_projects_page.py` cannot run at 390x844** | derived | the file's one viewport literal changed to `390x844`, suite run, then reverted byte-identical | `EEEEEEEE...EEEEEEEEEEEEEEEEEEEE` — **28 errors at fixture setup**, all `Page.click: Timeout 5000ms`, because the list column is collapsed by the drill-down below 760px. This is the measurement behind the C-8 `SCOPE_INCREASES` | qa-build | qa-build @ 2026-09-23 | `app.css:1962-1990` | current |
| `mypy --strict` on the harness package, against the tree's own convention | volatile | `.venv/bin/python -m mypy --strict tests/qa5`; then the same over `tests/web` | `tests/qa5`: **66 errors** (31 `explicit-any` from playwright's `Any` returns, 14 `call-overload` on `object` payloads, 13 `unused-ignore`). `tests/web`: **83 errors**. The env plan marks this row "not blocking for execution; reported" | qa-build | qa-build @ 2026-09-23 | `disallow_any_explicit = true` | current |
