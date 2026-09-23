# Test Environment Plan: Projects backend + dark-only web UI redesign (Shepherd / Flock / Projects / Settings) — QA round 5

**Workflow:** wf:wf-20260921T212808Z-9172ed6b · **Test plan:** `.cc10x/qa/wf-20260921T212808Z-9172ed6b/test-plan.md`
**Measured environment record:** `.cc10x/qa/env/Shepherd-local/setup.md` — preflight, 2026-09-22T21:39:30Z. **Where that record and this plan disagree, the measurement wins.** The disagreements are its §4, and all five are fixed below.
**Mode:** local · **Revision:** `r4` — a **preflight-driven environment amendment**
**Confirmed with user:** yes — the user authorised full autonomy for this run and is unavailable; the topology below was **given** to the planner in the dispatch brief (one `controld` per run on `127.0.0.1:0`, throwaway `HostPlatform`, real `Store` on a fresh DB migrated empty→004, headless chromium from the repo `.venv`, teardown by handle from the fixture that started it). No topology gate is raised. **This parenthesis is a verbatim quote of the brief and is left as written; `r4` (P1) measured that the *driver* is in the `.venv` and the *browser binary* is not — see §1, §7 and the correction table below. The topology the brief asked for is unchanged; only where the bytes live is.**
**Differences from agreement:** three, all forced by the tree and none of them discretionary:

1. **There is no `--data-dir` flag.** `shepherd-controld` takes `--port` and `--engine-config-dir` only (`src/shepherd/daemons/controld.py::parse_args`). The data directory is `host.dirs().data_dir`, i.e. `XDG_DATA_HOME/shepherd` on `LinuxHost`. The brief's "`--data-dir` under the session scratchpad" is realised as **`XDG_DATA_HOME` redirected into the session scratchpad**, with an arrival assertion that the resolved `data_dir` really is under it.
2. **"Injected throwaway `HostPlatform`" is realised as the real `LinuxHost` (via `detect_host()`) under a fully redirected environment**, not as `testkit.scripted_host.ScriptedHost`. A `ScriptedHost` stubs `detached_launch()` and the runtime dir, and the tmux/kill/terminal ground is exactly what round 5 exists to drive. This is the same idiom `tests/daemons/test_controld.py::world` already uses, including its "arrival, not trust" assertion.
3. **The `controld` is in-process, not a subprocess.** `compose._PLANE`, the registry and the stream ring are module-global (B10/ADR-7), so exactly one composition may exist per process; and every DB and audit-sink observation point in the test plan needs the `Store` handle that `controld.start()` returns. Teardown-by-pid therefore binds to the **child processes the fixture starts** — the chromium browser and the `shepherd-qa` tmux server — each closed through the handle that created it, never by `pkill` and never by a signal to `0`, `1` or `-1`.

> This plan is written only AFTER the topology was proposed on screen and the user confirmed it.
> The environment is the most expensive thing in a QA workflow to get wrong: a bad topology
> produces failures that look like product bugs, and that is precisely how a team learns to
> distrust its own test suite.

### Revision 4 — UNREVIEWED BY A FRESH PASS

**Revision 4 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap reached). This revision
was amended after the last fresh pass and has been checked only by amendment verification (not
run); no adversarial pass has read it whole. Sections changed since the last fresh review in **this
file**: §1 (the chromium row and its prose) · §2 (`$TMUX`, `XDG_RUNTIME_DIR`, the `live`
verification row) · §3 (the playwright, runtime-dir and collect-only rows, and the zero-human
paragraph) · §4 steps 1, 2, 3, 9 · §5 (P2, R3, "Reset between runs") · §7 (three rows, one of them
new) · §9 steps 8 and 9 and the leak check · §10 · §11 (B9, **new B20**, C-8, the owner census) ·
§12. Carried from `r3`: §4 step 10 · §5 (P2, R3) · §9 step 4 · §11 degradation.

**`r4` is a preflight-driven ENVIRONMENT amendment and nothing else.** No scenario, no contract and
no coverage claim changed. The 35 scenarios, the four partitions, §3a's control-footprint rule and
everything else pass 2 verified are untouched, and **`r3` remains what pass 2 reviewed.** What
changed is the environment *prediction* — and it changed because the machine was finally measured.
All five corrections are classed `wrong-guess` against this file; **none is a product defect.**

**Reaching the cap is a stopping point, not closure.** A plan that has spent both fresh-review
passes and is then amended is unreviewed at its current revision. The test plan's **§9a** carries
the sweep; read it as a stated gap, not as a review.

### What changed in `r4`

`qa-preflight` measured this host and returned `STATUS: FAIL` with five `ENV_PLAN_CORRECTIONS` —
**three blocking, two advisory**. Every one is this plan's error: an environment fact that cannot be
read out of source code, and was guessed here instead.

| # | What `r3` predicted | What the machine said | Fixed in |
| --- | --------------------- | ----------------------- | ---------- |
| **P1** | `PLAYWRIGHT_BROWSERS_PATH` "inherited; chromium-1243 already resolved in `.venv`" | Both halves are false. It is **unset**, and chromium is **not** in `.venv` — it is at `/root/.cache/ms-playwright/chromium-1243/`, a path playwright derives from `XDG_CACHE_HOME`/`HOME`, **both of which §7 redirects**. Measured under §7's own environment, `executable_path` resolves **without raising** to `<scratchpad>/xdg_cache/ms-playwright/…/chrome`, which does not exist: step 9 fails ~45 s into bring-up, looking like a chromium fault. Pinning `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` was measured to restore a full `launch()`/`inner_text`/`close()` under that same environment | §7 (row rewritten) · §4 steps 3 and 9 · §3's T2 row, which now runs **under the redirected environment** · §1 · §11 |
| **P2** | §2 names "any inherited `$TMUX`" — and §7 does not carry it | `$TMUX` **is** inherited and non-empty here, so the mitigation is live rather than hypothetical. But §7 is the section this plan states maps *mechanically* to `required_env`/`environment`, and a manifest generated from `r3`'s §7 would not unset it. Per `CLAUDE.md` rule 3, an inherited `$TMUX` resolves to **that session's own socket**, so `-L` on the session is not enough | §7 (**new `TMUX` (unset) row**) · §4 step 3 (an arrival assertion) · §2 |
| **P3** | §9 step 8 `rm -rf $SCRATCH`; §5 "each run creates a new scratchpad" | The session scratchpad is **long-lived and shared**: hundreds of prior artifacts (preflight counted **228**; the setup record's row says ~250 — the count is volatile, the sharedness is the fact) and, decisively, **`macwt` — a registered git worktree of `/root/Shepherd`** at `dade568`, detached, with `/root/Shepherd/.git/worktrees/macwt/gitdir` pointing into it. `rm -rf` destroys that checkout and leaves a corrupt registry entry — **and step 9's `git status --porcelain src/ tools/ docs/probes/` still reports empty.** A teardown that breaks the repo under test and certifies itself clean | §4 step 1, where `$SCRATCH` is **redefined once** as a minted run root · §5 · §9 steps 8–9 and the leak check · §10 · §11 **B20** |
| **P4** | B9: "the scratchpad path alone is ~88" | The scratchpad **root** is **76** bytes; **88** is the *subdir* form. Computed with the product's own `plan_socket`, the suffix `/shepherd/controld.sock` is **23** against a budget of **107** — confirmed empirically with real `AF_UNIX` binds, **107 BOUND, 108 REFUSED** — so the ceiling on `XDG_RUNTIME_DIR` is **84**. B9's conclusion survives for the form this plan intends; its premise described a different path than its prose | §2 · §3 · §4 step 2 · §7 · §11 B9 · feature map §5's B9 row |
| **P5** | the `live` gate reads the collected set for node ids **from `tests/e2e/`** | Three `tests/e2e/` node ids **are** collected by default, deliberately: `test_live_lane_typechecks.py` (2), whose docstring says *"This module carries no `pytest.mark.live`, and that is the whole point"*, and `test_live_master_isolation.py` (1). A path-based gate goes red on three intentional tests. The marker reading is exact as an integer: **live-marked 76 == deselected 76**, with 2226/2302 collected | §2 Verification · §3's collect-only row · test plan §1 and §3's flag table |

**What preflight CONFIRMED — by probe, not by repetition.** §3's claim of **zero `human`-owned
blockers** is confirmed: every prerequisite it names was probed present on this host (`setup.md` §3).
And C-8's premise holds — the node-id freeze is a genuine **subset** check, so adding `tests/qa5/`
is safe and only a *rename* needs a `RETIRED_NODE_IDS` entry.

### What changed in `r3`

Pass 2 returned 5 blocking and 11 advisory findings against `r2`; **five** of them land in this
file, all of them this plan's error:

1. **Step 10's rig control asserted one frame where the control is two** (F1). It created
   `RIG-PROBE`, asserted the `project.created` frame, then deleted it and asserted nothing — so the
   delete's `project.deleted` frame fell into **S0's** counted window, which is asserted as a zero.
   Both frames are now asserted, and the second is what opens the first counted window.
2. **P2's `(arm, then create)`** described a wire step that does not exist. `duplicate.armed` is
   page memory (`projects.js:620`, reset at `:547`); a fixture taking it literally issues **two**
   POSTs and creates **two** extra "Shepherd" workspaces, breaking S2's eight-rows rollup.
3. **§9 step 4 called `controld.stop(running)` unconditionally**, which is precisely what S29's
   cleanup forbids (*"`controld` is already stopped and `controld.stop` must not be called twice"*).
   The manifest is generated mechanically from §9, so the contradiction would have shipped.
4. **§11's tmux denominator was patched, not re-derived** — S16 was removed from the blocked set
   without re-walking the dependency graph, and **S9** was missed: it reads `len(DOOMED)` from S0's
   binding, and S0 needs a pane. The set is **9**, not 8, and it is re-derived below.
5. **§11's playwright row drew its loss on the tier partition only**, while five non-`ui`
   scenarios carry a named browser assertion each. Those five are now named.

### What changed in `r2`

Amended after a fresh review returned 6 blocking and 10 advisory findings, each re-verified against
its cited source before acceptance. Four of them land in this file: **the SSE client rig is now
attached and proved live in bring-up (§4 steps 10–11) and owned by the session fixture until
teardown**; **the seed provisions P5, P6, P7 and four panes**, because three test-plan scenarios
named fixtures this table did not provide; **R2 is consumed** by the scenario it was always seeded
for; and **§9's `tmux … kill-server` teardown step is dropped entirely** under router decision
**RD-QA5-1**. The test plan's §9 is the full amendment log.

**Maps 1:1 onto the harness manifest** (`templates/live-harness.template.json`). Section → key:
§4→`setup[]` · §5→`reset[]`/`seed[]` · §4 readiness→`healthcheck` · §7→`required_env`/`environment` · §9→`cleanup[]`.
Write these sections so `qa-harness-builder` can translate them mechanically, not creatively.

---

## 1. Topology

**How the system runs for testing:** one pytest process holds one composed `controld`, started once per run by a session-scoped fixture that first redirects every directory-bearing environment variable, then calls `controld.start(host=detect_host(), port=0, engine_config_dir=<throwaway>)`. That call is the whole product: it opens a real SQLite store (migrating empty → 004, so the database holds exactly the seeded `unassigned` workspace), composes the tool surface and **freezes the registry before the server binds**, starts the control-ingest listener, the discovery loop and the HTTP/SSE server on an ephemeral loopback port, and returns only once the control socket is bound. The harness reads the port off `Controld.port`. Alongside it the fixture owns two child worlds: a **tmux server on the throwaway socket `shepherd-qa`**, holding the real panes that make an *owned* session owned, and a **headless chromium** driven by the playwright package in `/root/Shepherd/.venv` — the browser *binary* is **not** in the venv (**`r4`, P1**: it is at `/root/.cache/ms-playwright/chromium-1243/`, which is why §7 pins `PLAYWRIGHT_BROWSERS_PATH`). Nothing else runs. No second server exists in the process, no port is fixed, and — **restated precisely in `r4`, because both halves of `r3`'s version had drifted** — **no path this run WRITES is outside its own run root `$SCRATCH` (§4 step 1)** except the one short runtime directory the 107-byte socket budget forces (P4); and the only path outside it the run **reads** is the chromium binary under `/root/.cache/ms-playwright` (P1). In particular the run never writes to, and never removes, the shared session scratchpad that contains its run root (P3).

| Service | Real or stubbed | Started by | Reachable at | Why stubbed (if stubbed) |
| --------- | ----------------- | ------------ | -------------- | -------------------------- |
| `controld` (HTTP + SSE + WS, tool registry, chokepoint, audit sink, discovery loop) | **real** | session fixture, `controld.start(detect_host(), 0, engine_config_dir)` | `http://127.0.0.1:{Controld.port}` | — |
| `Store` (SQLite, migrations 001→004) | **real** | `controld.start` → `open_store(host.dirs().data_dir / "shepherd.db")` | `Controld.store`, in-process handle | — |
| tmux server, socket `shepherd-qa` | **real** | session fixture, `tmux -L shepherd-qa new-session -d …` | `-L shepherd-qa` only | — |
| `LocalRunner` (pane driver, real kill path) | **real** | `compose.build_runner`, socket read from `app_state["runner_socket"]` | via the store handle | — |
| chromium 1243 (playwright 1.63) | **real** | session fixture, the `.venv` playwright **driver**; the **binary** is `/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome` (`Google Chrome for Testing 153.0.8010.12`), reached only because §7 pins `PLAYWRIGHT_BROWSERS_PATH` (**`r4`, P1**); headless | CDP, in-process handle | — |
| second SSE client (**and a first**: clients A and B) | **real** | **session fixture, at §4 step 10** — `http.client` reader threads (the `Subscriber` shape in `tests/daemons/test_controld.py`) | `GET /api/events` | — · **`r2`:** these were a *scenario* fixture in `r1`, attached inside S3 and left attached *"for wave 2"* with no owner stated past it — while S0, asserting **zero frames on the second SSE client**, ran as a bring-up gate **before any client existed**. Owner, lifetime and liveness proof are now test plan §3a |
| second browser tab | **real** | `context.new_page()` on the same chromium | — | — |
| `claude` engine / Agent SDK master | **absent, not stubbed** | nobody | — | **Never started.** `spawn_session` and `pytest -m live` start real `claude` processes against the user's real `~/.claude.json` and are forbidden in this workflow. Owned sessions are made owned by seeding a `RunnerHandle` over a pane the fixture created — see §5 and the §7 gap it earns in the test plan. |
| `sessiond` | **absent** | nobody | — | No scenario crosses the relay. `controld` binds the control socket itself and no frame is sent to it. Recorded so a reader does not read the absence as an oversight. |

**Every stub needs a justification.** A stub can *be* the bug — if a scenario fails, the harness must be able to rule out the stub before blaming product code. The only two absences above are absences, not stubs: nothing stands in for the engine, and a scenario that would need one is `BLOCKED`, never `FAIL`.

### Wiring

How services find each other: the browser and both SSE clients reach `controld` over loopback TCP at the port `controld.start` bound; every request carries `Host: 127.0.0.1:{port}` and every POST/stream carries `Origin: http://127.0.0.1:{port}`, because §13's origin **and** host check runs before the body is read on every POST and both streams. The runner finds tmux through `app_state["runner_socket"]`, which the fixture sets to `shepherd-qa` **before** `controld.start` — `compose.build_runner` reads it once at composition time and hands `permitted_sockets("shepherd-qa")` to the exec site, so every argv the product builds carries `-L shepherd-qa` explicitly and `check_tmux_argv` refuses anything else. `"shepherd"`, the user's own socket, is refused by name at that guard and is never written, never passed, and never enumerated by this harness.

Port allocation: **dynamic, `port=0`**, read back from `Controld.port`. No fixed port exists anywhere in the harness, so two runs on one machine cannot collide. The control and ingest sockets are Unix paths under the short runtime dir (§7), unlinked by `controld.stop`.

---

## 2. Feature flags, settings, and entitlements

This product has no feature-flag system. It has three pieces of **stored runtime state** that behave exactly like flags — they change which code path a request takes, they are set outside the request, and one of them is the difference between a kill that lands and a kill that cannot — so they are treated as flags here rather than declared `N/A`.

| Flag / setting | Where it is set | Default | Required value | Scope | Who can change it |
| ---------------- | ----------------- | --------- | ---------------- | ------- | ------------------- |
| `app_state["runner_socket"]` (D49/RD1) | `Store.set_app_state`, **before** `controld.start` | `"shepherd-runner"` (`tmux_cmd.DEFAULT_SOCKET`) | `"shepherd-qa"` | global (one per store) | harness fixture |
| `app_state["autonomy_level"]` (D8) | `Store.set_app_state`, or `POST /api/autonomy` | `2` (`tools_master.DEFAULT_AUTONOMY_LEVEL`) | `2` at bring-up; driven 2→3→2 by S26 | global | harness fixture and the product's own route |
| `XDG_*` / `HOME` / `TMPDIR` / `CLAUDE_CONFIG_DIR` | process environment, set before anything composes | the real user's | scratchpad (and the short runtime dir) | process | harness fixture |

**Cover each category that applies:**

- **Feature flags** — none exist; the three rows above are the honest equivalent.
- **Runtime config / env vars** — the directory family above. `XDG_RUNTIME_DIR` is the one that must **not** point into the scratchpad (B9).
- **Entitlements / licensing / plan tier** — `N/A`. Single-user, single-tenant, loopback-only; there is no tier.
- **Permissions and roles** — one caller identity exists: `caller_id="web"`, `Audience.HUMAN`, stamped by `web/server.py` and **unauthenticated by design**. There is no role to select. Measured consequence, and it matters for S26: `policy.TABLE` allows `LOCAL_DESTRUCTIVE` for `Audience.HUMAN` at **both** autonomy levels, attributed `claimed_human` — so the web caller never parks on an approval card and `delete_project` can never block on one. Any plan that expected the level-2 ask to gate a browser delete was wrong about this tree.
- **Org / tenant settings** — `N/A`, same reason as entitlements.
- **Kill switches and rollout percentages** — none exist.

### Flags that must be OFF

| Flag | Why it must be off |
| ------ | -------------------- |
| pytest's `live` marker | `pyproject.toml` `addopts = "-q -m 'not live'"` already deselects it. The harness must **never** override `addopts` in a way that re-selects it and must never pass `-m live`. `-m live` starts real `claude` processes against the user's real `~/.claude.json`. This is the constraint that makes AC-28's final clause unrunnable (C-4). |
| any inherited `$TMUX` | A command run inside tmux inherits `$TMUX` and resolves to **that session's** socket, so `-L` on the session is not enough (`CLAUDE.md` rule 3). Every tmux invocation in this harness passes `-L shepherd-qa` as `argv[1]` explicitly; `check_tmux_argv` enforces the same shape on the product side. **`r4` (P2): `$TMUX` is measured inherited and non-empty on this host**, so this row is live, not hypothetical — and in `r3` it was stated **only here**, in a section the manifest is not generated from. **§7 now carries a `TMUX` (unset) row**, which is the one that reaches `required_env`/`environment`, and §4 step 3 asserts its arrival. The inherited value is never transcribed, named or enumerated in these artifacts, and that socket is never written to. |
| `XDG_RUNTIME_DIR` pointing at the scratchpad | `controld` refuses to start (`SocketPathTooLong`) — B9, whose **conclusion stands and whose premise `r4` (P4) corrects**. The arithmetic, re-derived with the product's own `plan_socket` (`host/base.py:147-167`) and `LINUX_SOCKET_PATH_BUDGET` (`host/linux.py:42`), and confirmed by real `AF_UNIX` binds (**107 BOUND, 108 REFUSED**): budget **107**, fixed suffix `/shepherd/controld.sock` **23**, so the ceiling on `XDG_RUNTIME_DIR` is **84**. Measured candidates: session scratchpad root **76** → 99, *accepted*, margin +8 (the root alone would in fact fit — the plan never intended to use it); `<scratchpad>/xdg_runtime` **88** → 111, **refused by 4** — the form the plan intends, and the one `r3` mis-stated as "the scratchpad path alone"; the `r4` run root `$SCRATCH` (§4 step 1) ≤ **88** → ≤ 111, refused for the same reason; `/tmp/shq5-<pid>` **17** → 40, margin **+67**. Only the runtime dir is redirected to the short throwaway; data, config and cache stay in the scratchpad. |
| the `shepherd` tmux socket | The user's live sessions run there. It is never named in a write, never passed to any command, and **never enumerated even as a gate** — a check written as "`tmux -L shepherd ls` shows exactly N names" goes red the next time the user opens a terminal. |

### Verification

How the harness **confirms** each flag actually took effect — not that it was set, that it applied:

| Flag | Verification |
| ------ | -------------- |
| `runner_socket` | After `controld.start`, drive one real kill through the product (S11) and assert the pane is gone from `tmux -L shepherd-qa list-sessions`. A setting that did not apply produces a `RunnerRefusal` naming a different socket, which is a distinguishable failure, not a silent one. Cheap pre-check at bring-up: `Store.get_app_state("runner_socket") == "shepherd-qa"` read back **after** `controld.start`. |
| `autonomy_level` | `GET /api/autonomy` returns the level, and S26 reads the on-disk audit record's `decision`/`approved_by` for the call that changed it. Asserting the POST returned 200 proves the POST returned 200. |
| directory redirects | The `world`-style arrival assertion, copied from `tests/daemons/test_controld.py`: resolve `detect_host().dirs()` **after** the redirect and assert the scratchpad is a parent of `data_dir` and `config_dir`, and that the short throwaway is a parent of `runtime_dir`. Without this the fixture is happy to hand back the real user's directories. |
| `live` deselected | **`r4` (P5): the gate is on the MARKER, not on a path.** Two `--collect-only` runs in preflight — the default (`addopts = -q -m 'not live'`) and `-m live` — with the counts compared **as integers**: live-marked **must equal** deselected. Measured **76 == 76**, at **2226/2302** collected. `r3`'s path reading — *"no node id from `tests/e2e/` or `tests/web/test_render_live.py::…`"* — is **false of this tree**: three `tests/e2e/` node ids are collected by default **on purpose**, `test_live_lane_typechecks.py` (2), whose docstring says *"This module carries no `pytest.mark.live`, and that is the whole point"*, and `test_live_master_isolation.py` (1). A harness implementing the path reading goes red on three intentional tests and reports it as a gate failure. T4 tier. |

> Flag state is also a **scenario dimension**, not only setup. A feature behind a flag needs coverage with it ON *and* OFF — see test plan §3.

---

## 3. Prerequisites

| Requirement | Owner | Cost tier | Check command | How to acquire | If missing |
| ------------- | ------- | ----------- | --------------- | ---------------- | ------------ |
| repo at branch `integration`, HEAD `c243773` | harness | T1 | `git -C /root/Shepherd rev-parse HEAD` | already checked out; **no pull, no fetch, no checkout** without an answered currency gate | BLOCKED — the whole plan is written against this tree |
| `docs/probes/` unmodified (frozen evidence) | harness | T1 | `git -C /root/Shepherd status --porcelain docs/probes/` → empty | n/a | **BLOCKED and reported.** Never repair by editing; a capture edited to look tidy stops being evidence |
| `src/` unmodified by QA | harness | T1 | `git -C /root/Shepherd status --porcelain src/` → empty at start and at end | n/a | BLOCKED — QA never edits product code |
| `/root/Shepherd/.venv/bin/python` exists | harness | T1 | `test -x /root/Shepherd/.venv/bin/python` | n/a — measured present | BLOCKED |
| playwright importable, and chromium launchable **under the harness's own redirected environment** | harness | T2 | `/root/Shepherd/.venv/bin/python -c "import playwright"`; then a real `chromium.launch()`/`inner_text`/`close()` **run with §7's environment applied** — `HOME` and `XDG_CACHE_HOME` redirected **and `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` set** — plus `os.path.exists(p.chromium.executable_path)` asserted | `python -m playwright install chromium` | BLOCKED. **Assert it, never assume it** (B13): `js_syntax_check.py` and `render_check.py` both sit behind `importorskip` for an undeclared dependency, so a machine without playwright **collects and passes** — a silently-skipped gate that reports green. **`r4` (P1): and assert it under the environment the harness will actually use.** `r3`'s check ran under the *inherited* environment, where it passes; under §7's it resolved `executable_path` to a non-existent file **without raising**, and the failure surfaced ~45 s later at bring-up step 9, looking like a chromium fault. A prerequisite check that cannot see its own harness's failure is not a prerequisite check |
| `tmux` on PATH, version readable | harness | T2 | `tmux -V` (the one argv allowed without `-L`; it contacts no server) | `apt-get install tmux` | BLOCKED for waves 4 and parts of 3; the rest of the plan still runs (§11 degradation) |
| `git` on PATH, and a real repository on disk for `add_repo` | harness | T2 | `git --version`; then create one under the scratchpad | `git init` a throwaway repo in the scratchpad with one commit | BLOCKED for the `add_repo`/`remove_repo` rows — `probe_repo` shells out to git with **no stub seam** (B11) |
| a short writable runtime directory (**≤ 84 bytes** — the measured ceiling, §2/B9; the chosen form spends **17**) | harness decision | T2 | `mkdir -p /tmp/shq5-$$ && test -w /tmp/shq5-$$`; then the budget asserted as an integer with the product's own `plan_socket` | created by the fixture | BLOCKED — `controld` refuses to start (B9). **`r4` (P4): the ceiling is 84, not "~40"** — 40 is what `/tmp/shq5-<pid>` *spends* once the 23-byte suffix is added, and `r3` conflated the two |
| loopback bindable | harness | T2 | bind `127.0.0.1:0`, read the port, close | n/a | BLOCKED |
| sqlite3 module + migrations 001–004 present | harness | T1 | `ls src/shepherd/store/migrations/` → four files | n/a | BLOCKED |
| `pytest --collect-only` green, and **live-marked == deselected** | harness | T4 | `/root/Shepherd/.venv/bin/python -m pytest --collect-only -q`, then the same with `-m live`; the two counts compared as integers (§2 Verification). **`r4` (P5): marker-based, never path-based** | n/a | BLOCKED |
| `mypy --strict` clean on the harness package | harness | T4 | `/root/Shepherd/.venv/bin/python -m mypy --strict tests/qa5` | fix the harness | Not blocking for execution; reported |

A missing prerequisite is **BLOCKED**, never FAIL. Environment problems must never be converted into a verdict about product code.

**`Owner: human` with an empty `How to acquire` fails this plan's own completeness bar.** There are **no `human`-owned prerequisites in this run** — every row above is checkable and, where absent, installable by the harness. **`r4`: that is now confirmed by probe rather than asserted by the planner.** `qa-preflight` measured every row present on this host and `setup.md` §3 records *"None"*: git 2.43.0, tmux 3.4, `.venv` Python 3.12.3, playwright 1.63.0 with a chromium-1243 that really launches, `/tmp` writable with 24 GiB free (~2600× the measured screenshot footprint), loopback bindable, four migrations on disk, `docs/probes/` / `src/` / `tools/` clean. **One clause of `r3`'s sentence was wrong and is corrected above**: chromium-1243 is present but is **not in `.venv`** (P1).

**`Cost tier` orders preflight, and the ordering is the point.** Nothing in a higher tier runs until every lower tier is green.

| Tier | What belongs here | Typical cost |
| ------ | ------------------- | -------------- |
| `T1` | static existence — nothing is executed against a service | ms |
| `T2` | local probes — nothing is *started* | seconds |
| `T3` | reachability of things already running that we did not start | seconds |
| `T4` | cheap builds and gates | 10s–1min |

**T3 is empty in this run, deliberately**: nothing this harness talks to is already running. Everything it uses, it starts. Recorded rather than omitted, because an empty T3 is the property that makes the run reproducible on a clean machine.

There is no T5. **Booting a service is not preflight** — it belongs to `qa-build` / `qa-execute`.

---

## 4. Bring-up → manifest `setup[]` + `healthcheck`

| # | Step | Command | Readiness signal | Timeout |
| --- | ------ | --------- | ------------------ | --------- |
| 1 | **Mint the run root and create its tree — the session scratchpad is NOT fresh** | `SESSION_SCRATCH=/tmp/claude-0/-root-Shepherd/<uuid>/scratchpad` (given, long-lived, **shared**); **`SCRATCH="$SESSION_SCRATCH/qa5-$$"`**; `mkdir -p $SCRATCH/{xdg_data,xdg_config,xdg_state,xdg_cache,home,tmp,engine-config/sessions,work,shots,repo}`; capture `git -C /root/Shepherd worktree list` as the teardown baseline. **First**, the §10 sweep: remove any `$SESSION_SCRATCH/qa5-*` and `/tmp/shq5-*` whose pid is **not alive**, reporting each removal — and nothing else, ever, by any other pattern | the sweep reported what it removed; **`$SCRATCH` did not exist when it was minted** (a survivor with a *live* pid means a concurrent run — stop, do not delete it); every directory exists; the worktree baseline is captured and non-empty. (**`r4`, P3.** `r3`'s `tmp` directory was also missing here while §7 sets `TMPDIR=$SCRATCH/tmp` — found while re-deriving this step, fixed in the same breath) | 5s |
| 2 | Create the **short** runtime dir | `mkdir -p /tmp/shq5-$$` | `test -w`; and the budget asserted **as an integer, with the product's own arithmetic** — `len(XDG_RUNTIME_DIR) + len("/shepherd/controld.sock") <= LINUX_SOCKET_PATH_BUDGET`, i.e. `17 + 23 = 40 <= 107`, margin **+67** (`plan_socket` at `host/base.py:147-167`; the budget at `host/linux.py:42`, and measured by real `AF_UNIX` bind: **107 BOUND, 108 REFUSED**). The ceiling on the directory itself is **84** (**`r4`, P4**) | 5s |
| 3 | Redirect the environment — **all ten rows of §7, which is the whole table** | set `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `HOME`, `TMPDIR` → under `$SCRATCH`; `XDG_RUNTIME_DIR` → `/tmp/shq5-$$`; `CLAUDE_CONFIG_DIR` → `$SCRATCH/engine-config`; **`PLAYWRIGHT_BROWSERS_PATH` → `/root/.cache/ms-playwright`** (`r4`, P1); **`TMUX` unset** (`r4`, P2) | `detect_host().dirs()`: `$SCRATCH` is a parent of `data_dir` **and** `config_dir`; `/tmp/shq5-$$` is a parent of `runtime_dir`. **Arrival, not trust** — and **two more arrivals for the two `r4` added**, both of which `r3` had no way to fail: `os.environ.get("TMUX") is None`, and `os.path.exists(p.chromium.executable_path)` is **True** with the resolved path under `/root/.cache/ms-playwright` | 5s |
| 4 | Open the store and set the socket knob | `open_store(data_dir/"shepherd.db")`; `set_app_state("runner_socket","shepherd-qa")`; close | `user_version == EXPECTED_SCHEMA_VERSION`; `list_projects()` is exactly one row, id `unassigned` | 15s |
| 5 | Start the tmux server and the owned panes | `tmux -L shepherd-qa new-session -d -s shepherd_r5a -x 160 -y 45`; likewise `shepherd_r5b`, **`shepherd_r5c`**, **`shepherd_r5d`** | `tmux -L shepherd-qa list-sessions -F '#{session_name}'` lists **all four**. **`r2`:** `r1` created two and the plan spent them four times — the ledger is test plan §3b | **10s** (**`r3`:** this cell was **empty** — step 5 was the one row in a table §4 says is translated *mechanically* into the manifest's `setup[]` with no timeout at all, i.e. an unbounded wait on tmux, which is the failure this section's own closing paragraph forbids) |
| 6 | Start `controld` | `controld.start(host=detect_host(), port=0, engine_config_dir=$SCRATCH/engine-config)` | **the call returns** — it does not return until the control socket's `bound` event is set (`BIND_TIMEOUT_S=10`). `Controld.port != 0`; the control socket path exists | 20s |
| 7 | Functional readiness probe | `GET /api/fleet` with `Host: 127.0.0.1:{port}` | HTTP 200 and `{"ok": true}`; retried on a bounded loop, never `sleep N` | 10s |
| 8 | Seed the world (§5) | store verbs + HTTP front door, per §5 | the seed assertions in §5 | 30s |
| 9 | Launch chromium | `sync_playwright().start().chromium.launch(headless=True)` | a page navigates to `/` and `document.readyState == "complete"`. (**`r4`, P1:** this is where `r3` would have failed, ~45 s into bring-up and looking like a chromium fault — §7 redirected `XDG_CACHE_HOME`/`HOME` and left `PLAYWRIGHT_BROWSERS_PATH` inherited-and-unset, so `executable_path` resolved **without raising** to a file under the scratchpad that does not exist. Step 3's arrival assertion now fails **at step 3** instead, ~40 s earlier and naming the real cause) | 30s |
| 10 | **Attach the SSE rig, prove it live, and run the three fixture-side controls** | attach clients **A** and **B** to `GET /api/events`; create `RIG-PROBE` via `POST /api/projects` and assert **one** `project.created` frame at **both**; then delete it and assert **one `project.deleted` frame at both** — **two frames, the control's full shape (test plan §3a), and the `project.deleted` frame is what OPENS the first counted window**. (**`r3`, F1:** `r2` asserted only the create here, so the delete's frame was asserted nowhere and fell into S0's counted window at step 11 — which S0 asserts as a **zero**.) Then §3c's controls: create `shepherd_r5z`, assert it is listed, `tmux -L shepherd-qa kill-session -t '=shepherd_r5z:'`, assert it is **not** listed; round-trip each seeded `RunnerHandle` through `Store.set_runner_handle` → read-back; `Store.get_app_state("runner_socket") == "shepherd-qa"` | every assertion above. **A failure here is `BLOCKED` and bring-up stops** — never a product verdict | 30s |
| 11 | **S0 runs here, as a measurement** | see test plan §4 S0 | `killable`/`unkillable`/`doomed` read off a real refusal and bound to a plan variable, **with S0's own in-scenario liveness control closing the window** | 30s |

**`$SCRATCH` is defined at step 1, once, and it is NOT the session scratchpad (`r4`, P3).** From
`r4` onward, **every `$SCRATCH/<sub>` path in all three artifacts denotes
`$SESSION_SCRATCH/qa5-<pid>/<sub>`** — the per-run root minted at step 1 and removed at §9 step 8.
`$SESSION_SCRATCH` is the long-lived, **shared** session directory: preflight found hundreds of
prior artifacts in it and, decisively, **`$SESSION_SCRATCH/macwt` — a registered git worktree of
`/root/Shepherd`** at `dade568`, whose registry entry is `/root/Shepherd/.git/worktrees/macwt/gitdir`.
`r3`'s teardown said `rm -rf $SCRATCH` meaning *that* directory: it would have deleted a checkout of
the repo under test, left a corrupt registry entry, **and still reported `git status --porcelain
src/ tools/ docs/probes/` empty at §9 step 9** — a teardown that breaks the repo and certifies
itself clean. **Nothing in this run removes `$SESSION_SCRATCH`, and nothing in this run writes
outside `$SCRATCH`** except `/tmp/shq5-<pid>`. This is the single definition site; no other section
restates the expansion, and a reader who needs it comes here.

**Step 10 exists because `r1` did not have it.** S0 asserted *zero frames on the second SSE client*
at this exact point, and nothing in steps 1–9 attached one; and S11 — the first kill this project
has ever driven against a real pane — had no way to distinguish a broken product from a wrongly
seeded handle. Step 10 is both: the rig, proved live, and the mechanics, proved fixture-side.

**`sleep N` is not a readiness signal — it is a race condition with a comment.** Every wait above gates on something real: an event object, a bound port, a 200, a listed pane, a `readyState`. Bound the wait, and fail loudly when the bound is hit.

**Readiness has a named blocker (B1): there is no health or readiness endpoint.** The closest proxy is `GET /api/fleet`, which needs a working store and can fail for reasons unrelated to liveness. So readiness is **two signals, not one**: step 6's `bound` event (a real signal the product itself sets, and the only one that is purely about liveness) and step 7's functional probe. A step-7 failure after a clean step 6 is `BLOCKED` — an environment verdict — not a product `FAIL`.

---

## 5. Data → manifest `reset[]` + `seed[]`

**Isolation model:** ephemeral-everything

| Model | Strength | Cost |
| ------- | ---------- | ------ |
| Ephemeral everything | Strongest | Slowest |
| Fresh data, shared services | Usually the right trade | Requires a reliable reset |
| Namespaced in a shared env | Weakest — leaks read as flake | Only when the others are impossible |

Ephemeral is chosen rather than traded for: the store is a single file under a scratchpad, migrating it from empty costs well under a second, and the alternative — resetting a shared database — would have to undo a `delete_project` cascade that is the destructive subject of five scenarios. **Never test against an environment someone else is using.** Nothing here is shared with the user's own `shepherd` socket, `~/.claude`, or any live process.

**Schema / migrations:** `open_store(path)` migrates a new file from empty through `001_m1_foundation.sql`, `002_m2_stop_verdicts.sql`, `003_m3_mailbox.sql`, `004_projects.sql`, and 004 seeds the reserved `unassigned` workspace. The harness asserts `user_version == EXPECTED_SCHEMA_VERSION` and that the fresh database holds **exactly one** workspace before seeding. No SQL is executed by the harness against the database directly — the storage boundary forbids it and a direct sqlite open would be the harness's own defect.

**Seed set — `n > 1` everywhere. This is the single most load-bearing paragraph in the plan.** Nine of eleven round-1 defects were invisible at `n = 1`: every prior fixture seeded one project and at most two sessions, **all attached**, so `DeletePlan.killable` was empty in every test that ever read it, no two projects shared a name, and no path was long enough to ellipsise. The seed is therefore specified as a shape, and each element earns its place:

| # | Entity | Value | Built via | Why it must exist |
| --- | -------- | ------- | ----------- | ------------------- |
| P0 | workspace `unassigned` | seeded by migration 004 | migration | the reserved project: Edit and Delete are **absent, not disabled**, on it; the `orphan` destination |
| P1 | workspace "Shepherd" | 2 repos, long description | `POST /api/projects` + `POST …/repos/add` | the ordinary project |
| P2 | workspace "Shepherd" (**duplicate name**) | 0 repos | **exactly one** `POST /api/projects {"name": "Shepherd"}` | the duplicate-name warn/re-arm chain **as a page behaviour driven by S33(c)**; no prior fixture ever had two projects sharing a name. **`r3`: `(arm, then create)` was a wire step that does not exist.** `duplicate.armed` is page memory (`projects.js:620`), reset on every dialog open (`:547`), and `store.create_project` is a bare INSERT with no name check (`store/projects.py:52-70`). A fixture that arms and then creates issues **two** POSTs and makes **two** extra "Shepherd" workspaces — breaking test plan S2's *"eight workspaces / eight rows"* |
| P3 | workspace "Flock" | 1 repo at a path ≥ 935 px when rendered — a real directory nested ~12 levels under the scratchpad | `git init` + `POST …/repos/add` | the ellipsis/`title` attribute path; and `add_repo` needs a **real** git repo (B11) |
| P4 | workspace "Doomed" | 0 repos | `POST /api/projects` | S0's subject: the project that gets deleted |
| **P5** | workspace "Attached-only" | 0 repos | `POST /api/projects` | **Added in `r2`.** The project with **only attached** running sessions and **no pane**. S10's case (b) and the whole of S12 named this fixture and `r1` provisioned none — `r1` put running sessions in P4 alone and spread S-att-2..4 "over P1 and P3", so no attached-only project existed and none was designated |
| **P6** | workspace "Orphan-subject" | 0 repos | `POST /api/projects` | **Added in `r2`.** S13's own project. S13 needs 1 owned + 1 attached + 3 finished, and in `r1` **every pane was spoken for** — its owned session had no pane at all |
| **P7** | workspace "Stale-handle" | 0 repos | `POST /api/projects` | **Added in `r2`.** S17's own project, whose owned session points at a pane the fixture kills inside the scenario |
| S-own-1 | session in P4, **OWNED**, `runner_handle = local\|shepherd-qa\|shepherd_r5a`, `ended_at` NULL | store: `register_session` + `set_runner_handle` | the only way `killable` is ever non-empty — a real pane on the throwaway socket |
| S-att-1 | session in P4, **ATTACHED**, `runner_handle` NULL, `ended_at` NULL | store: `register_session` | `unkillable`: alive with no pane of ours. The shipped kill answers `no_pane` for it |
| S-fin-1..3 | three **finished** sessions in P4 | store: `register_session` + end them | `doomed` must be a number a dialog can show *before* the button; three, so "and N finished ones go with it" is not 1. S-fin-4..6 are P6's, for the same reason |
| S-own-2 | session in P1, **OWNED**, handle over pane `shepherd_r5b` | store | the terminal-WebSocket subject (wave 4), and a second owned session so no assertion can pass by picking "the" owned one |
| **S-own-3** | session in **P6**, **OWNED**, handle over pane **`shepherd_r5d`**, `ended_at` NULL | store | **Added in `r2`.** S13's owned session — the one `r1` left without a pane |
| **S-own-4** | session in **P7**, **OWNED**, handle over pane **`shepherd_r5c`**, `ended_at` NULL | store | **Added in `r2`.** S17's stale-handle subject; the fixture kills `shepherd_r5c` inside S17, after this row exists |
| S-att-2..4 | three attached sessions spread over P1 and P3, varied `started_at` | store | Flock cards at `n > 1`; date-scale classes |
| **S-att-5, S-att-6** | two attached sessions in **P5**, `runner_handle` NULL, `ended_at` NULL | store | **Added in `r2`.** What makes P5 attached-**only**: `killable` empty with `running` non-empty, which is S10 case (b)'s entire subject |
| **S-att-7** | attached session in **P6**, `ended_at` NULL | store | **Added in `r2`.** S13's second running session — `orphan` must move both |
| **S-fin-4..6** | three **finished** sessions in **P6** | store: `register_session` + end them | **Added in `r2`.** S13 asserts `destroyed` names three, so three must exist in its own project |
| R1 | a real git repo, one commit, at `$SCRATCH/repo/plain` | `git init` | `add_repo` happy path |
| R2 | a **non-git** directory at `$SCRATCH/work/notgit` | `mkdir` | `add_repo` refusal path — **consumed by S34**. **`r2`:** in `r1` this row said the same thing while the test plan's §2 and §7 both declared non-git-dir *uncovered* and **no `add_repo` refusal was driven at all** — a fixture provisioned and never used, and a flat contradiction between the two artifacts |
| **R3** | a regular **file** at `$SCRATCH/work/afile` | `touch` | **Added in `r2`.** The **non-directory** value from the feature map's nine; driven by **S33(e)**, in `#dlg-project`'s **edit** mode. **`r3`, F4:** `r2` drove (d) and (e) in **create** mode, where `#p-paths-section` is hidden (`projects.js:549`) and `addDraftPath` returns before any request (`:586`) — so R3 was seeded, named, and **consumed by nothing**, the same shape `r2` corrected for R2. It is also now listed in test plan §1's `Seeded world`, which is what *"Preconditions: as §1"* inherits |
| **panes** | `shepherd_r5a`, `shepherd_r5b`, `shepherd_r5c`, `shepherd_r5d` at §4 step 5, and `shepherd_r5z` at step 10 | `tmux -L shepherd-qa new-session -d` | **One pane per owning scenario** — the ledger is test plan §3b. `r5z` is the fixture-side kill control (§3c) and is destroyed by the control itself |

**Timestamps are seeded far from every boundary** (B12: `app.js:115` calls `Date.now()` directly in `drawFlock`, so the page-level clock is not injectable in a browser run). Every seeded `started_at`/`last_event_at` sits at least 2× away from the nearest bucket edge of the relative-time scale — e.g. 400 days, 40 days, 40 hours, 40 minutes — so a run that takes ten minutes cannot walk a value across a threshold. The "just now" (<60 s) class is asserted only at the API seam, never in the browser.

**Two seams, and the difference is declared, not blurred.** P1–P4, their repos and their descriptions are built **through the product's own front door** (`POST /api/projects`, `…/rename`, `…/description`, `…/repos/add`) — a fixture written straight into the datastore can encode a state the application cannot produce, and then the suite tests fiction. The **sessions** are seeded through `Store` verbs, because the only front door that creates one is `spawn_session`, which starts a real `claude` process and is forbidden. That is a real reduction in fidelity and it earns a row in the test plan's §7 known gaps: a store-seeded owned session is a row that *looks* owned to every reader, and what it does not prove is that the spawn path produces that shape.

**Reset between runs:** none — there is nothing to reset. Each run mints a **new run root** `$SCRATCH` (§4 step 1), a new database file inside it, a new tmux server and a new browser, and destroys all four (§9). **`r4` (P3) corrects what `r3` claimed here**: the *session* scratchpad is **not** fresh per run — it is long-lived, shared, holds hundreds of prior artifacts and a registered git worktree of the repo under test, and **is never destroyed by this run**. Freshness is a property of the run root this plan mints, not of the directory it mints it in, and the difference is the whole of P3. Between scenarios, each scenario's own `Cleanup` line in the test plan restores what it changed; scenarios that destroy a project (S11, S13) use **their own** project — P4 and P6 — never a project a later scenario reads, and wave 3's fixed order is **S9, S10, S12, S11, S13** so that S12's read of **P5** does not wait behind the pane destruction in S11.

**Every `LIVENESS-<scenario-id>` project is part of the seed's contract, not a scenario's improvisation.** Test plan §0 rule 4 requires each frame-counting scenario to create and delete one; they are throwaways, they are never one of the mutations under test, and each scenario's `Cleanup` line names its own.

---

## 6. Determinism

| Source of nondeterminism | Control | Seam |
| -------------------------- | --------- | ------ |
| Time / clock | Seed absolute timestamps ≥2× away from every relative-time boundary; assert relative strings only at classes that cannot move within a run's wall clock. The composed `utc_now` is **real** and is not shimmed — a shim moves thresholds, not ticks, and the discovery loop's 2.0 s cadence would be unaffected anyway | `store.register_session(started_at=…)`; `flock.js::ago` takes the clock as a parameter (unit seam exists, browser seam does not — B12) |
| Random / ID generation | `correlation_id` is `uuid4().hex` per request with **no injection point** (B17): match a 32-hex **pattern**, never a value. Session and workspace ids are ulids minted from the wall clock: read them back, never spell them | `server.py:123`; `store.register_session` return value |
| External network calls | There are none. Bind is `127.0.0.1` only with no knob. The single subprocess boundary is `git` (via `probe_repo`, B11) against repositories the harness created on disk, and `tmux` against `shepherd-qa` | `probe_repo`; `LocalRunner.run_argv` |
| Concurrency / ordering | The ring's `id:` is a monotonic `seq` — assert monotonicity and set-equality of the frames, never arrival order across two independent clients. `refreshAll` coalesces to at most two passes with no timer, so assert "at most two", never "exactly one". Every wait is bounded (10 s) and a blown bound is `BLOCKED`/`TIMEOUT`, never a product `FAIL` | `sse.frame()`; `app.js:253-288` |
| Rollout percentage / sampling | `N/A` — no sampling exists anywhere in this product | — |
| **SSE tail-subscription window** | `sse.py:124-128` records an **unclosed** window (BLOCKER T15-1): a tail subscriber can miss an event published in the instant between subscriptions. The code states the gap and does not close it. **The rig is therefore attached exactly once, at §4 step 10, and never re-attached by a scenario** — re-attaching is the one operation that can walk into this window. Every scenario that counts frames drives a known-good control mutation **inside its own body** and asserts its **two** control frames — `project.created` then `project.deleted`, in that order — so a zero-frame reading is a product fact and not this window. (**`r3`, F1:** this said *"exactly one control frame"*, one of the two spellings of the control the amendment reconciled; test plan §3a is the single definition.) **`r2`:** this rule was stated here and in S5 and was obeyed by **S5 alone** — S0, S9, S10, S11, S12 and S17 all counted frames without it, and S0 counted them before any client was attached. It is now test plan §0 rule 4 and §3a, and it binds every one of them | `sse.stream(since_seq)` |
| **Fixed waits already in the tree** | The existing browser gates use a fixed 700 ms after navigation and 350 ms after a nav click, with a stated **no-retry** flake policy (B16). Round 5 keeps no-retry — *"a flaky render check is a render check that has stopped being evidence"* — and replaces fixed sleeps with bounded predicate waits wherever it writes new browser code | harness |

If a test can pass or fail depending on the wall clock, it will eventually do both.

---

## 7. Secrets and config → manifest `required_env` + `environment`

**There are no secrets in this run.** Nothing authenticates, nothing calls out, and `caller_id` is an unauthenticated self-stamp. The table is directories.

**This table is the environment contract, and it is the whole of it (`r4`, P2).** §2 states rules in
prose; **§7 is what the manifest's `required_env`/`environment` is generated from**. A fact stated
in §2 and missing here does not reach the harness — which is exactly how `r3` named the inherited
`$TMUX` hazard in §2 and shipped a table that would not have unset it. Two rows are new or rewritten
in `r4` for that reason, and `$SCRATCH` below is the **run root** minted at §4 step 1, never the
session scratchpad. **The table is ten rows** — `r3`'s nine plus `TMUX` — and §4 step 3 sets
exactly those ten and asserts the **arrival** of five: `XDG_DATA_HOME` and `XDG_CONFIG_HOME` (via
`dirs().data_dir`/`config_dir`), `XDG_RUNTIME_DIR` (via `dirs().runtime_dir`), `TMUX` (absent from
`os.environ`) and `PLAYWRIGHT_BROWSERS_PATH` (via an `executable_path` that exists on disk). The
other five are set and not separately asserted, which is stated rather than left to be assumed.

| Variable | Source | Notes |
| ---------- | -------- | ------- |
| `XDG_DATA_HOME` | fixture → `$SCRATCH/xdg_data` | `data_dir = $XDG_DATA_HOME/shepherd`; holds `shepherd.db` and `logs/` (the audit sink) |
| `XDG_CONFIG_HOME` | fixture → `$SCRATCH/xdg_config` | |
| `XDG_STATE_HOME` | fixture → `$SCRATCH/xdg_state` | redirected even though `LinuxHost` does not read it — `MacHost` does, and a fixture that redirects only the platform it was written on hands the other one the developer's real home |
| `XDG_CACHE_HOME` | fixture → `$SCRATCH/xdg_cache` | same reason |
| `HOME` | fixture → `$SCRATCH/home` | same reason |
| `TMPDIR` | fixture → `$SCRATCH/tmp` | same reason |
| `XDG_RUNTIME_DIR` | fixture → `/tmp/shq5-<pid>` | **The one path this run WRITES outside its own run root, and it is forced** (the only path it *reads* outside is the chromium binary — see the last row but one). **`r4` (P4), measured:** budget **107** (107 BOUND, 108 REFUSED on real `AF_UNIX` binds), suffix `/shepherd/controld.sock` **23**, ceiling on this variable **84**. `<scratchpad>/xdg_runtime` is **88** → 111, refused by 4; the run root `$SCRATCH` is ≤ 88, refused for the same reason; this form is **17** → 40, margin **+67**. (`r3` said "the scratchpad path alone is ~88"; 88 is the subdir form, the root is 76 — B9's conclusion holds, its premise did not.) Owner: `harness decision` (§11). Holds `shepherd/controld.sock`, `shepherd/sessiond.sock` and the pane sink directory. Removed in teardown |
| `CLAUDE_CONFIG_DIR` | fixture → `$SCRATCH/engine-config` | the throwaway engine config dir, also passed as `--engine-config-dir`. **Nothing in this run may read or write `~/.claude` or anything under `/root/.claude/`** |
| `PLAYWRIGHT_BROWSERS_PATH` | **fixture → `/root/.cache/ms-playwright`** | **`r4` (P1) — the correction that would otherwise have cost 45 s of bring-up and looked like a product fault.** `r3` said *"inherited; chromium-1243 already resolved in `.venv`; not overridden"*, and **both halves are false**: the variable is **unset** on this host, and the browser is not in `.venv` — the playwright *package* is, the *binary* is `/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome`, on a path playwright derives from `XDG_CACHE_HOME`/`HOME`, **which the four rows above redirect**. Left inherited, `executable_path` resolves **without raising** to `$SCRATCH/xdg_cache/ms-playwright/…/chrome` and `exists = False`. Pinned explicitly, a full `launch()`/`inner_text`/`close()` was measured green under exactly this environment |
| **`TMUX`** | **fixture → UNSET** (removed from the environment, not set empty) | **`r4` (P2) — new row.** Measured **inherited and non-empty** on this host. `CLAUDE.md` rule 3: a command run inside tmux inherits `$TMUX` and resolves to **that session's own socket**, so `-L` on the session is not enough — which is both why every invocation passes `-L shepherd-qa` as `argv[1]` *and* why this row must exist here rather than only in §2's prose. The inherited value is **never read into any artifact, never transcribed, never named and never enumerated**; the socket it names is not this run's business |

**No real credentials, ever.** There is no credential to supply, so there is no `human_action` checkpoint in this run.

Two absolute read prohibitions, from the workflow's `qa.isolation`, restated here because a harness reads this file and not the workflow JSON: **never read anything under `/root/.claude/**`**, and **never read any `*.key` file**. Also denied: `/root/shepherd-backup-20260920/**`, `/root/pre-orchestrator-backup-20260720/**`, `/root/AIVisor/**`, `/root/Finopsera_poc/**` — the first two are stale copies of this same repo, and citing them would report old code as current.

---

## 8. Observability access

| Service | Log source | Access method | Structured? |
| --------- | ------------ | --------------- | ------------- |
| `controld` audit sink | `$XDG_DATA_HOME/shepherd/logs/<AUDIT_PREFIX>/<date>.jsonl` (`RotatingJsonlLog(log_root(host), AUDIT_PREFIX)`, `log_root = data_dir/"logs"`) | read the files off disk after the call; the harness resolves `AUDIT_PREFIX` from `shepherd.daemons.plane`, never by spelling the string | **yes**, JSONL, one record per gated invoke |
| `controld` stop log | `$XDG_DATA_HOME/shepherd/logs/<STOP_PREFIX>/…` | same | yes |
| `controld` stdout | not captured — the in-process fixture never runs `main()`, so the `controld: http://…` banner is not emitted | `N/A` in this topology; recorded so nobody writes an assertion against it | no |
| HTTP error envelope | the response body itself | `{"ok":false,"data":null,"error":"GENERIC_ERROR","correlation_id":"<32 hex>"}` | yes |
| anomaly counters | `Store.list_anomaly_counts()` | in-process store handle | yes |
| stream ring | `GET /api/events` | the SSE clients themselves; `: open` and `: keep-alive` are comment lines and are skipped as such, so "no frame arrived" stays distinguishable from "the socket is alive" | yes |
| browser | `console` and `pageerror` events | playwright listeners registered **before** the first navigation; any `console.error` or `pageerror` fails the scenario, as the six existing browser test files already do | no — text |
| tmux | `tmux -L shepherd-qa list-sessions -F …` | the fixture's own invocation, `-L` explicit | yes |

A scenario cannot assert a log line the harness has no way to read. The one unreadable source above (`controld` stdout) is named rather than silently skipped.

---

## 9. Teardown → manifest `cleanup[]`

**Order matters: the browser first, because a page holding an SSE connection keeps a server thread busy; then the server; then tmux; then the files.**

| # | Step | Command | Verification |
| --- | ------ | --------- | -------------- |
| 1 | Close every page and context | `page.close()` / `context.close()` per handle | no open contexts on the browser handle |
| 2 | Close chromium | `browser.close()`; then `playwright.stop()` | the launch handle reports closed. **By handle, never `pkill`, never a signal to `0`, `1` or `-1`** |
| 3 | Close every SSE reader | `Subscriber.close()` per handle | reader threads joined, bounded 5 s |
| 4 | Stop `controld` — **conditionally** | **if** the composition is still running, `controld.stop(running)`; **else** skip the call and assert it is already down | **`r3`:** `r2` ran `controld.stop(running)` **unconditionally**, and **S29 stops the daemon as its own `When` and its cleanup says in terms that `controld.stop` must not be called twice**. §9 is translated mechanically into the manifest's `cleanup[]`, so the contradiction would have shipped into the harness. Verification branches: **stopped here** → returns a `ShutdownOutcome` reporting **no hung thread**, and both socket paths no longer exist; **already stopped by S29** → the call is not made, and both socket paths are asserted **already** gone. The run report records which branch ran, because "teardown skipped the stop" and "teardown never reached the stop" are different facts |
| 5 | Kill the QA panes, one by one, **by name** | `tmux -L shepherd-qa kill-session -t '=shepherd_r5a:'` (and `…r5b`, `…r5c`, `…r5d`, and any pane a scenario created) | each returns 0 or "session not found" — **"session not found" is the expected answer for `r5a`, which the product destroyed inside S11, and for `r5c`, which the fixture destroyed inside S17** |
| 6 | Assert the socket is empty | `tmux -L shepherd-qa list-sessions -F '#{session_name}'` | **no session remains.** `-L` explicit. This is the assertion that replaces `r1`'s `kill-server` step |
| 7 | Remove the short runtime dir | `rm -rf /tmp/shq5-<pid>` | path gone |
| 8 | Remove the **run root only** | `rm -rf $SCRATCH` — i.e. `$SESSION_SCRATCH/qa5-<pid>`, the directory §4 step 1 minted. **`$SESSION_SCRATCH` is never removed** | `$SCRATCH` gone; `$SESSION_SCRATCH` still present; **`$SESSION_SCRATCH/macwt` still present**. (**`r4`, P3:** `r3` wrote the same command meaning the *session* directory, which holds hundreds of prior artifacts and a **registered git worktree of `/root/Shepherd`**. It would have destroyed that checkout and corrupted `/root/Shepherd/.git/worktrees/macwt/gitdir`) |
| 9 | Prove the repo is untouched — **including its worktree registry** | `git -C /root/Shepherd status --porcelain src/ tools/ docs/probes/`; **and `git -C /root/Shepherd worktree list`, compared against the baseline captured at §4 step 1** | the first is **empty** (`docs/probes/` is frozen evidence; `src/` is product code QA never edits); the second is **identical to the baseline**. (**`r4`, P3:** the `status` line **alone** is what made `r3`'s teardown self-certifying — deleting `$SESSION_SCRATCH/macwt` leaves `src/`, `tools/` and `docs/probes/` clean and the registry corrupt, and this step would have signed it off. A changed, pruned or vanished worktree entry is a **`BLOCKED` finding about this harness**, never a product verdict) |

**`r2`, RD-QA5-1: the `tmux -L shepherd-qa kill-server` step is dropped entirely.** `r1`'s usage was
compliant — `-L` explicit, a throwaway socket, after the panes were already killed by name — and the
reviewer confirmed it. It is gone anyway, by router decision, for the reason that it **buys
nothing**: step 5 is what frees the panes, and the old step 6 was self-described as
"belt-and-braces". What it did carry was the **exact verb of the 2026-09-12 incident**, where a
`kill-server` opened a spike as a "clean slate" step and destroyed three live sessions including the
one that issued it. A teardown that ends by *asserting* the socket is empty proves the same property
and cannot be copied into a context where the `-L` is missing. There is now **no `kill-server` in
this plan at any blast radius.**

**Teardown must verify itself.** "Ran the cleanup" is not evidence.

**Leak check** (**`r4`: seven**, and all seven are assertions, not observations):

```
ss -ltnp | grep -F ":{port}"                 # → no output
tmux -L shepherd-qa list-sessions             # → "no server running" or empty
pgrep -P <pytest pid> -f chromium             # → no output   (children of OUR pid only)
git -C /root/Shepherd status --porcelain src/ tools/ docs/probes/   # → empty
git -C /root/Shepherd worktree list           # → identical to the §4 step 1 baseline   (r4, P3)
test ! -e /tmp/shq5-<pid> && test ! -e $SCRATCH            # the RUN ROOT, not the session dir
test -d $SESSION_SCRATCH && test -d $SESSION_SCRATCH/macwt # never ours to delete   (r4, P3)
```

The chromium check is deliberately scoped to **children of this process**, never a machine-wide `pgrep chromium`: a machine-wide match would go red because the user has a browser open, and a gate that goes red for someone else's work gets turned off. The tmux check names **only** `shepherd-qa`. `tmux -L shepherd ls` is never run, not even to confirm it is unchanged: the user's live sessions are not this run's business, and enumerating them as a gate is how a check ends up asserting a session-name list that changes the next time they open a terminal. Round 3's teardown was *self-verified rather than asserted*; round 5's is asserted.

**Flag restoration:** `autonomy_level` is driven 2→3→2 by S26 and the store it lives in is deleted at step 8, so restoration is structural. Nothing global-scope is flipped: every setting this run touches lives inside the throwaway store or the throwaway environment.

---

## 10. Re-runnability

**Proven by running twice back-to-back with no manual cleanup between runs.** The second run is not optional and not a formality: state collisions and stale state hide behind a single run.

| Check | Result |
| ------- | -------- |
| Second run passes | to be filled by `qa-execute` — the **same** verdict per scenario id, or the difference is a finding |
| No port collisions | expected clean: `port=0` everywhere, no fixed port in the harness |
| No leftover fixtures | expected clean: a new **run root** (`$SCRATCH`, §4 step 1), a new DB file inside it, a new tmux server, a new browser per run. **`r4` (P3): re-runnability rests on the run root's pid-named uniqueness, not on the session directory being empty** — it is shared and it is never empty |
| Flags still in required state | expected clean: every setting lives in the deleted store or the deleted environment |

One known re-run hazard, recorded in advance: if run 1's teardown is interrupted, `/tmp/shq5-<pid>` survives with a stale socket, and **`r4` adds its twin — an abandoned `$SESSION_SCRATCH/qa5-<pid>` run root.** The pid is in both names, so run 2 cannot collide with either; the harness sweeps `/tmp/shq5-*` **and `$SESSION_SCRATCH/qa5-*`** whose pid is not alive at bring-up, and reports what it removed rather than removing silently. **The sweep matches `qa5-<pid>` only** — it never removes an entry it did not name, which is the rule the `macwt` worktree exists to teach.

---

## 11. Blockers and open decisions

| # | Item | Owner | Blocks | Resolved? |
| --- | ------ | ------- | -------- | ----------- |
| B1 | **No health or readiness endpoint.** The only liveness proxy is `GET /api/fleet`, which needs a working store | external (product shape) | nothing — worked around | **worked around**: readiness is the `bound` event **plus** a functional probe, and a probe failure after a clean bind is `BLOCKED`, not `FAIL` |
| B2 | `render_check.py` is **structurally blind** to intra-page grid collapse: `#page-flock`'s rectangle is byte-identical healthy and broken, and Chromium reports the implicit grid track so both read as three rows | harness | any grid-collapse assertion | **resolved by design**: S24 measures the **panes** (`#proj-list`, `#proj-detail`), never the root. No per-root rectangle can distinguish those |
| B3 | **Vacuous containment over self-sizing boxes** — a 307,418 px container passed every "content fits its box" assertion | harness | every containment assertion | **resolved by design**: every containment assertion is against the **viewport**, never the parent |
| **B18** | **A "non-zero box" is a one-pixel floor**, and an undefined "clickable" degrades to "present in the DOM" — the mirror image of B3, on the property the plan itself names as the one most able to look proven while proving nothing | harness | PP-7 and every pane-health assertion (S19, S22, S23, S24, S25) | **`r2`, resolved by design**: test plan **§3d** defines `HIT_TESTABLE` and `PANE_HEALTHY` once. The floor is the product's own `FILL_FLOOR = 0.75` (`tools/render_check.py:87`), which **no `r1` scenario used**, plus a containment relation no 1 px box can satisfy |
| **B19** | **A frame count with no liveness control passes on a dead socket** — and `r1`'s riskiest instance asserted zero frames at a point in bring-up where no SSE client had been attached at all | harness | every frame-counting assertion | **`r2`, resolved by design**: test plan **§0 rule 4** and **§3a**; the rig is attached and proved live at §4 step 10 and owned by the session fixture to teardown step 3 |
| B4 | A module-graph walk certifies a **fetch, not a call** — `flock.js` was "reached" while the page never drew | harness | reachability claims | **resolved by design**: no round-5 scenario asserts reachability; every UI claim is a measured DOM or pixel fact |
| B5 | A lexical `try`-scan cannot see whether the `catch` does anything — a silent `catch {}` satisfies it | harness | error-path claims | **resolved by design**: every error path is driven, and the assertion is the rendered sentence, not the presence of a `try` |
| B6 | **Green suites over unpopulated fixtures** — every prior fixture seeded one project and at most two sessions, all attached | harness | the whole plan's credibility | **resolved**: §5's `n > 1` seed, with one owned session, one duplicate name, one ellipsising path and three finished sessions |
| B7 | `app_state["kill.<id>"]`'s null-row distinction is **not observable through any `Store` verb** — only a direct sqlite open could see it, which the storage boundary forbids | external | that one distinction | **not resolved — scoped out.** No scenario asserts it; carried as a known gap |
| B8 | `web/server.py` is **byte-pinned** and `_CONTENT_TYPES` is `.html`/`.js`/`.css` only | external | fixture staging | **binding constraint**: **no font, image, SVG or JSON fixture may enter the static tree.** Every fixture this run needs is a store row, an HTTP body or a file outside `src/shepherd/web/static/` |
| B9 | `controld` refuses to start with `XDG_RUNTIME_DIR` inside the scratchpad | harness decision | bring-up | **resolved**: only the runtime dir points at `/tmp/shq5-<pid>`; the budget is asserted as an integer at step 2, never assumed. **`r4` (P4) corrects the premise, and the conclusion survives it.** `r3` said "107-byte budget, scratchpad path ~88". Measured: the budget **is** 107 (107 BOUND, 108 REFUSED on real `AF_UNIX` binds); the suffix `/shepherd/controld.sock` is **23**, so the ceiling on `XDG_RUNTIME_DIR` is **84**; the scratchpad **root** is **76** → 99, *accepted* with margin +8, and **88 is the subdir form** `<scratchpad>/xdg_runtime` → 111, refused by 4. The run root `$SCRATCH` (≤88) is refused for the same reason and `/tmp/shq5-<pid>` (17) → 40 has margin +67. So: the intended form really is refused, the chosen form really does fit, and the number `r3` quoted described a different path than its prose |
| **B20** | **The session scratchpad is long-lived and SHARED, and it contains a registered git worktree of the repo under test** — `$SESSION_SCRATCH/macwt` at `dade568`, detached, registry entry `/root/Shepherd/.git/worktrees/macwt/gitdir` — alongside hundreds of prior artifacts | harness decision | teardown | **`r4`, resolved by decision**: the run mints and removes **only** `$SCRATCH = $SESSION_SCRATCH/qa5-<pid>` (§4 step 1, §9 step 8), and §9 step 9 asserts `git worktree list` is **unchanged across the run** against a baseline captured at bring-up. The builder must state in `setup.md` that it implemented the run-root form. **Why this is a blocker and not a footnote:** `r3`'s `rm -rf $SCRATCH` would have destroyed that checkout **and passed its own verification**, because `git status --porcelain src/ tools/ docs/probes/` is empty either way |
| B10 | Registry, stream ring and `compose._PLANE` are **module-global** — two servers cannot coexist in one process | harness decision | parallelism | **resolved**: one `controld` per process, scenarios serial. Parallel **processes** would be fine; parallel threads are not. The harness must not use `pytest-xdist` within this package |
| B11 | `add_repo` shells out to git via `probe_repo` with **no stub seam** | harness | every `add_repo` row | **resolved**: real repositories created on disk under the scratchpad (R1, R2) |
| B12 | The **page-level clock is not injectable** — `app.js:115` calls `Date.now()` directly | external | relative-time assertions in a browser | **worked around**: seed absolute timestamps far from boundaries; assert the `<60 s` class at the API seam only |
| B13 | `js_syntax_check.py` and `render_check.py` both need playwright and **neither declares it** in `pyproject.toml` — a machine without it collects and **passes** | harness | trust in those gates | **resolved for this run**: preflight T2 asserts playwright is importable *and* that a real `chromium.launch()` succeeds. The undeclared dependency itself is a defect already routed out to a ticket — not ours to fix |
| B14 | `tests/web/test_ws.py`'s 14 reader tests assert a contract with **no implementer** — vacuous by construction | external | nothing here | **scoped out and declared**: round 5 drives the WebSocket **write** half over the wire (S14/S16) and makes no claim about those 14 |
| B15 | `pre_m4_routes.json` freezes only the **pre-T24** surface; the nine Projects/M4 routes are additive-checked only | external | route-contract confidence | **not resolved — scoped out.** A change to the delete body contract would pass that gate; carried as a known gap |
| B16 | Stated flake policy is **no retries**, with fixed 700 ms / 350 ms waits | harness | browser stability | **kept**: no retries. New browser code uses bounded predicate waits instead of fixed sleeps |
| B17 | `correlation_id` is `uuid4().hex` per request with **no injection point** | external | error-envelope assertions | **worked around**: match a 32-hex pattern, never a value |
| C-8 | **`viewport-drift` is still open**: `tests/web/test_projects_page.py` and `test_settings_live.py` hard-code 1280x900 and reference `render_check.VIEWPORTS` **zero times** — the exact drift that hid D1 | harness | not this plan; the existing suite | **handed to `qa-build`**, with its node-id retirement entries. Closing it rewrites node ids; the freeze in `tests/boundaries/test_collected_node_ids.py` is a **subset** check, so *adding* round-5 files is safe and *renaming* existing ones needs a `RETIRED_NODE_IDS` entry. **`r2`:** round 5 must not reproduce the drift it is complaining about — `r1`'s scenarios hard-coded their widths while the test plan claimed they read `VIEWPORTS` by reference, and **only S30 did**. Round 5 now has **one** definition site of its own, `ROUND5_WIDTHS` (test plan §3d), read by reference by S21–S24. **`r3`:** that claim was still one member too wide in `r2` — **S22's `Preconditions` hard-coded `1280x900`** while §3d and §7 both credited it with reading the constant. S22 now reads it. Coverage was never wrong; the **one definition site** the C-8 repair turns on was still two, and a restated constant is this tree's signature defect. **`r4`: preflight confirmed the premise this row rests on** — `subset_violations(baseline_node_ids(), live, RETIRED_NODE_IDS) == []` at `tests/boundaries/test_collected_node_ids.py:309`, with `RETIRED_NODE_IDS` at `:37`. It really is a subset check, so **adding `tests/qa5/` is safe** and only a rename needs a retirement entry |
| E1 | **Round 1's eleven closures cannot be re-verified** — recorded with no id, no description and no named check | external | nothing runnable | **declared, never re-proved.** Round 5 does not trust them and does not attempt to re-derive them |

Anything preventing the environment from being built, including work owned by another team. **An unresolved blocking item stops the harness build** — do not build against an unresolved contradiction.

### Owner is a classification, and it decides who waits

| Owner | Meaning | Who unblocks it |
| ------- | --------- | ----------------- |
| `human` | Only a person can supply it | The user, and the harness build waits |
| `harness` | Mechanical: an install, a pin, a preflight check | The harness build itself, at build time |
| `external` | Owned by another team or a deployed system | Nobody here — record it, scope around it |
| `harness decision` | A choice the harness must make and then state | The builder, who must name which behaviour it implemented |

**Audited, and downgraded where the measurement allowed it.** The instinct is to mark everything `human` because it is unresolved right now, and that instinct is expensive. **`r4`: the audit is now confirmed by probe rather than by the planner's own reading.** `qa-preflight` measured on this host: tmux 3.4, git 2.43.0, `.venv` Python 3.12.3, playwright 1.63.0 with a chromium-1243 that really launches, `/tmp` writable with 24 GiB free, loopback bindable, four migrations on disk, `docs/probes/` / `src/` / `tools/` clean, `XDG_RUNTIME_DIR=/run/user/0` real. **There are zero `human`-owned blockers in this run, and that is now a measured fact** (`setup.md` §3). The one clause `r3` got wrong is P1's: chromium-1243 is present but **not in `.venv`**.

**The owner census, re-derived by counting the table above rather than carried forward (`r4`).** **22 rows**: **11 `harness`** (B2, B3, B18, B19, B4, B5, B6, B11, B13, B16, C-8) · **3 `harness decision`** (B9's runtime-dir path, B10's one-process rule, and **B20's run-root teardown** — the builder must state in `setup.md` which form it implemented for each) · **8 `external`** (B1, B7, B8, B12, B14, B15, B17, E1) · **0 `human`**. `r3` said *"Two are `harness decision`"* — B20 did not exist yet — and *"Seven are `external`"*, **which was a slip**: it read the *un-closable* list as the external one. They are different sets, and B8 is the difference: it is `external` **and** closable by compliance (no font, image, SVG or JSON fixture enters the static tree), so it belongs in one list and not the other. **`r2`: "the tmux teardown shape in §9 step 6" is no longer a decision at all.** RD-QA5-1 settled it: there is no `kill-server` step, teardown ends at the by-name kills plus an emptiness assertion, and the builder has nothing to choose there.

**Genuinely un-closable by the harness: B1, B7, B12, B14, B15, B17, E1 — seven.** **Unchanged by `r4`**: B20 is closable, and it is closed. That is the real ask, and none of it blocks the run.

### Degradation — what the suite still proves when a blocker stays open

| Unresolved blocker | What still runs | What is lost | Must the run report say so? |
| -------------------- | ----------------- | -------------- | ----------------------------- |
| tmux unavailable (prerequisite fails) | waves 1 (minus S0), 2, 5, 6, and **S16** — the one member of wave 4 that needs no pane — **26 of 35** scenarios | **`BLOCKED`: S0, S9, S10, S11, S12, S13, S14, S15, S17 — 9 of 35 (26%).** **`r3`: re-derived from the dependency graph, not patched.** `r2` reached 8 by *removing* S16 from `r1`'s list — the patching method §2 says was abandoned — and so kept **S9**, which is blocked, out of it. The derivation, stated once so the next revision can re-run it: (1) no tmux → no panes → §3c's handle round-trip control is red → **S0** cannot bind truthfully, and a binding off a fixture bug is `BLOCKED`, not `B-EMPTY`; (2) every scenario whose `Preconditions` read **`S0 bound`** goes with it — **S9, S10, S11, S12, S13**, which is the whole of wave 3. S9 is in this set because its UI row compares `#dlg-delete-doomed` against `len(DOOMED)` **from S0's binding** and §2 says *"until S0 returns, none of these five is interpretable"*; (3) every scenario that names a pane directly — **S14, S15** (`shepherd_r5b`), **S17** (`shepherd_r5c`). Union: **9**. **S16 is not in it**: it drives the `no_pane` branch off a missing handle and contacts no tmux (`toolsurface/tools_terminal.py:228-237` → `web/server.py:296-308`), which is now also stated in test plan §3's wave-4 `Stop-if` and in S16's own `Preconditions` — `r2` had it here and **nowhere else**, and the test plan blocked the whole of wave 4 | **yes** |
| playwright/chromium unavailable | waves 1–4 and the wire half of 6 at the API/store seams — **13 of 35 fully, plus 5 partial** | every `ui`-tier scenario `BLOCKED` (**17 of 35, 49%**), including all of wave 5, which is where round 5's undriven ground lives. **`r3`: the loss is NOT drawn on the tier partition alone.** Five **non-`ui`** scenarios each carry a **named browser assertion** in their `UI` row, and without chromium each would record PASS with one named assertion unevaluated — the rounding-up test plan §0 rule 2 forbids, in the table whose whole point is that no loss is absorbed. They are: **S2** (`#proj-list` shows eight rows; P2's empty-state sentence), **S6** (`#p-desc-note` reflects the cleared state after a reload), **S12** (open the dialog and read `#dlg-delete-live`'s refusal), **S13** (after a reload the Flock still shows the two orphaned sessions under Unassigned), **S16** (the session pane renders the no-pane sentence). Each is recorded **`PARTIAL`, with the unevaluated assertion named**, never as `PASS`. A run in this state should be reported as **not worth its name** | **yes** |
| git unavailable | everything except the repo rows | S2's repo assertions and P1/P3's repo seeding degrade to zero-repo projects; `add_repo`/`remove_repo` rows `BLOCKED`, **including S32's add/remove chain and S34's `add_repo` refusal over R2** — `probe_repo` shells out to real `git` with no stub seam (B11) | **yes** |
| B1 (no health endpoint) | everything | nothing — but a readiness failure is reported as `BLOCKED`, and a reader must not read it as a product defect | **yes** |
| B7, B14, B15, B17, E1 | everything | specific claims, each already a §7 known gap in the test plan with its own "what a PASS does NOT prove" line | **yes** |
| **`pytest -m live` forbidden (C-4)** | everything else | **AC-28's final clause is not executed.** The substitute is a served-`controld` render sweep over `render_check.VIEWPORTS` carrying no `live` marker (S30). A PASS on S30 does **not** discharge AC-28 | **yes — verbatim, with the reason** |

**Every loss is stated in the run report, never absorbed.** A suite that quietly drops 60% of its scenarios and reports PASS is worse than one that fails, because it manufactures confidence.

If nothing can be provisioned at all, set `ENV_MODE: manual_instructions` and stop at a `human_action` checkpoint. That is not this run: every prerequisite was measured present.

---

## 12. Real time cost

| Item | Cost | Reducible? |
| ------ | ------ | ------------ |
| Full bring-up (steps 1–11) | **~45–65 s** — store migrate <1 s, compose + bind ~1 s, tmux panes ~1 s, chromium launch ~3–8 s, seed ~10 s (the `git init` repos and the HTTP-front-door seeding dominate) | Marginally. The browser launch is once per run, not per scenario |
| Slowest scenario family, and why | **Wave 5, ~5–8 min.** **Nine** UI scenarios, several sweeping the **nine** measured widths (320, 390, 760, 761, 820, **900**, 1280, 1920, 2560) across six page roots, each with a bounded settle and a screenshot. S23 and S24 alone are ~50 page-loads. **`r2` correction:** `r1` called this list *seven* and the test plan's §2 called the same list *eight* while its own S24 prose added 900 — the measured set was always **nine**, and both artifacts now say so | Yes, by dropping viewports — but the widths above 1280 and below 390 are precisely the ground that has never been driven, so cutting them is cutting the yield |
| Full-suite wall clock | **~11–16 min** for all **35** scenarios, serial, one process. Wave 1 ~1 min · wave 2 ~1.5 min · wave 3 ~2 min · wave 4 ~1.5 min · wave 5 ~6 min · wave 6 ~3 min. Bring-up gains step 10's rig proof and three fixture-side controls (~5 s). **`r3` adds, and the wave totals absorb it:** the in-scenario control is **two** HTTP calls in each of **13** scenarios rather than one in twelve (§0 rule 4's re-derived cell (iii) adds **S19**) — ~13 extra sub-second POSTs; S19 and S33 each open `#dlg-project` **once more** to reach edit mode (~2 page interactions each); S32's Save now issues one `…/description`; S34 creates and deletes one decoy. **Total added: well under 30 s**, inside the band already quoted, so no wave estimate moves | Not without losing coverage. Parallelism is unavailable (B10) inside one process |
| Second run (re-runnability, §10) | doubles it: **~22–32 min** total for the two runs | No — one run proves nothing about the second |

**A clock shim moves thresholds; it does not move ticks.** Patching `Date.now` makes age comparisons cross their thresholds instantly and leaves `setInterval`/`setTimeout` exactly where they were. Two timers on this path have **fixed rates** and no scenario should be written as if they could be moved:

| Timer | Rate | Controllable? | Cost to a scenario that waits on it |
| ------- | ------ | --------------- | ------------------------------------- |
| discovery loop cadence | 2.0 s, owned by `run_discovery_loop` | **no** — not a parameter of `controld.start` | ≥2 s real per pass waited on. No round-5 scenario waits on a discovery pass; if one is added, it costs 2 s and the plan must say so |
| SSE keep-alive comment | fixed in `sse.py` | **no** | irrelevant: keep-alives are comment lines and are skipped, so no scenario waits for one |
| approval timeout | 600 s (`APPROVAL_TIMEOUT_S`) | n/a | **never reached in this run**: `Audience.HUMAN` is allowed at both autonomy levels, so no web call parks on a card. Recorded because a plan that assumed the level-2 ask gated a browser delete would have written a 600 s hang into its own harness |

Patching the timer wheel is the wrong trade here and is not proposed: it decouples virtual time from the event loop and makes bounded re-checks fire in orderings the product never produces.

### `r4` reconciliation — what moved, and the derivation that shows what did not

`r4` changes the environment, not the work. The re-derivation is shown rather than asserted,
because "nothing moved" is exactly the claim a reader cannot check on trust:

- **Step numbering is unchanged.** §4 is still **11 steps**, §9 is still **9 steps**: `r4` adds no step to either. The run-root mint is absorbed into step 1 (which already created directories), the two new variables into step 3 (which already set eight), the worktree baseline into step 1's capture, and the worktree comparison into step 9's existing verification cell. **Every cross-reference elsewhere in the three artifacts — "§4 step 5", "§4 step 10", "§9 step 3", "§9 step 4", "§9 step 8" — therefore still resolves to the same step**, which was checked by search across all three files, not assumed.
- **Bring-up cost.** Added: one `mkdir -p` of a run root (**<10 ms**), one `git worktree list` (**~10 ms**), two environment assignments and one `unset` (**0**), and two arrival assertions at step 3, `os.environ.get("TMUX") is None` and `os.path.exists(executable_path)` (**<5 ms**, both in-process). **Total well under 0.1 s** against a band of **45–65 s**: the band does not move. If anything `r4` makes bring-up *cheaper on the failing path*, since the step-9 failure `r3` needed ~45 s to reach now fails at step 3 in under a second.
- **Teardown cost.** Added: one `git worktree list` and a comparison against the captured baseline (**~10 ms**). And `rm -rf` of a run root is *cheaper* than `rm -rf` of the session directory — which is the operation `r4` removes, not adds.
- **Wall clock.** **~11–16 min** for 35 scenarios and **~22–32 min** for the two runs are **unchanged**. No scenario was added, removed or re-scoped, and no scenario's work changed.
- **Denominators.** Nothing partitioned moved, and this is checkable rather than asserted: the 35 scenarios, the four partitions, the **9**-scenario tmux-blocked set, the **17** `ui` scenarios, the **5** `PARTIAL` non-`ui` browser rows, the **nine** measured widths and §2c's **seventeen** PP ids are each a function of scenario content, and **no fact P1–P5 corrected is an input to any of them**. The one number `r4` does move is §11's owner census (2 → **3** `harness decision`, 7 → **8** `external`, the second a correction of an `r3` slip), re-derived there by counting the table.
- **The socket arithmetic is the one place a number changed, and it changed to a measured one**: budget **107** (bound at 107, refused at 108), suffix **23**, ceiling **84**, scratchpad root **76**, `xdg_runtime` subdir **88**, run root **≤88**, `/tmp/shq5-<pid>` **17** → 40. B9's conclusion is unchanged; only its premise was wrong.
- **Screenshot footprint, now measured rather than trusted**: one nine-width sweep is **220 KiB**, S23+S24's ~50 loads ≈ **1.2 MiB**, a generous 400 shots ≈ **9.5 MiB** against **24 GiB** free — ~2600× headroom. No scenario's cost estimate depends on it, and no wave total moves.
