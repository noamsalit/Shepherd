# The M1–M4 QA harness — what was built, what it found, 2026-09-18

Plan: `docs/plans/2026-09-18-m1-m4-qa-plan.md`. Harness: **`tests/qa/`**, nine
scenarios, **all nine built**. 45 deterministic tests in the default lane and 18
in the live lane, over 10 modules.

Every number below was measured on this tree during this pass. Every scenario
carries a mutation that was applied in a per-task shadow and observed RED.

| what | before | after |
|---|---|---|
| default sweep | 1791 passed, 1 skipped, 57 deselected | **1836 passed, 1 skipped, 75 deselected** |
| `tests/boundaries` | 105 passed | **105 passed** |
| `mypy --strict src` | 126 files clean | **126 files clean** |
| live lane (`pytest -m live`) | 57 passed | **75 passed, 1837 deselected** |
| `wc -l src/shepherd/daemons/controld.py` | 140 | **140** |
| `sha256 ~/.claude/settings.json` | `375e5322…d6ac` | **`375e5322…d6ac`** |
| `tmux -L shepherd ls` | `m3`, `master` | **`m3`, `master`, unchanged** |

`tests/qa/` runs in the default lane; S8 and S9 carry
`pytestmark = pytest.mark.live` because they start real processes on this host.
**No product code was edited.** Two test-side edits were needed and both are
recorded below.

---

## The defects this pass found

Five, and the first two are the kind this pass existed to look for: each one is
a property of the *composition*, invisible from inside any single milestone.

### D1 · A session the master spawns can never reach the wake set — **critical**

`store/reads.py::WAKE_ORIGIN` is `Origin.ORCHESTRATOR`, so `wake_candidates`
selects `WHERE origin = 'orchestrator'`. **Nothing in `src/` ever creates a
session with that origin.**

| writer | origin |
|---|---|
| `tools_m3.SPAWN_ORIGIN` — *every* spawn through the tool surface, master's included | `Origin.USER_UI` |
| `signals/hook_lane.py`, `signals/discovery_loop.py` | `Origin.EXTERNAL` |
| `orchestration/ask.py` | `Origin.ASK_FORK` |

`Origin.ORCHESTRATOR` appears twice in `src/` and neither is a write: the
`WHERE` clause above, and `admission.MASTER_ORIGIN`, which the retry cap
compares against.

So **D31's wake set is structurally empty in production.** The whole chain the
spec draws — master spawns → session stops → M2 classifies → the next turn opens
with it — cannot fire, and every existing test of the wake set passes because
each writes its own row with `origin=ORCHESTRATOR` directly.

Held by `tests/qa/test_s2_spawn_stop_wake.py::
test_a_session_the_master_spawned_can_never_reach_the_wake_set`, which drives a
real `invoke("spawn_session")` as `Audience.MASTER`, stops that row through M2's
own lane, and asserts the drain over it is empty — with a positive control on a
row that *can* wake, so the emptiness is about the composition and not about a
broken reader. Both constants are imported, never respelled; the check goes red
the day they agree.

### D2 · §12's Needs-You rail never sees an approval — **high**

§12's own mock has three row kinds and the third is an M4 approval
(`1 approval pending · work_item_set_status`). `rail.js` renders
`fleet_summary`'s `needs_you` list and, in its own words, **"composes nothing"**;
`fleet_summary` builds that list from one source — rows whose `effective_state`
is `NEEDS_YOU` — through `project_needs_you`, which whitelists five *session*
columns. There is no reader of `ApprovalStore.pending()` anywhere in
`tools_m1.py`, and the composition hands `fleet_summary` a `Store` and a clock.

A pending approval — the thing a person must answer for a blocked master turn to
continue — is therefore **invisible on every page's rail**. `rail.js`'s own
comment says M4 was to add it; it was not added, and nothing failed.

Held by `tests/qa/test_s4_needs_you_rail.py::
test_a_pending_approval_never_reaches_the_needs_you_rail`, with a real card
raised through the shipped gate on another thread and asserted *pending* before
its absence from the projection is asserted.

### D3 · `shepherd status` tells a user to start a daemon that is already running — **high**

M1's T18-1 says the registry is a process global. What that costs a user was
never observed, because every prior assertion was made in-process, where the
question cannot be posed. Measured beside a **real running `controld`**:

```
shepherd: fleet_summary did not answer: request failed (correlation_id=…).
The tool surface this process sees has no such capability registered —
start the shepherd control daemon, or run this command against a host where
it is running.
```
exit `1`.

The daemon *is* running, on this host, serving HTTP on its port with its control
socket bound. `test_a_status_with_no_daemon_at_all_says_the_same_thing` drives
the no-daemon case and gets byte-identical advice — so the running daemon
contributes nothing to what the user sees, and the advice is actively wrong.
`shepherd doctor` succeeds in the same environment, which is what makes this a
finding rather than a broken install.

Held by `tests/qa/test_s8_status_against_a_daemon.py` (live).

### D4 · A worker released at shutdown **always** raises — §T25-8 is not a race — **medium**

§T25-8 records that a worker freed by shutdown's withdrawal "can" meet a closed
store. The shipped check asserts `page_answer[0]["is_error"] is True`, which is
true in **both** branches — `client.call` answers an error mapping on a refusal,
and the test's own `except` writes the same key on a raise — so it cannot say
which happens.

Measured over **20 runs of the full composed shape: 20 raises, 0 refusals.** The
released caller comes back with `RuntimeError("store is closed")` every time;
D54's refusal is never what it gets. The hazard is deterministic on this host,
not intermittent.

Clause 20 still holds: nobody is left blocked, and the release beats the card's
own `deadline_at` on every run, so it is a release and not a timeout.

Held by `tests/qa/test_s7_shutdown_in_flight.py`, which records the two branches
separately, asserts `branches == {RAISED}` so the repair is visible, and proves
its own recorder can produce both.

### D5 · Two usability findings from the first real install — **low**

Both invisible to `tests/test_packaging.py`, which reads the manifest as data
and builds a wheel without running anything:

* `shepherd --help` → `unknown command '--help'`, exit 64. The usage block
  follows, so nobody is stranded, but the message is wrong about what happened:
  `--help` is not an unknown *command*, it is the conventional spelling of the
  thing being printed. This is the second thing anybody types.
* `shepherd-sessiond` → `argparse` error, exit 2: `--expected-schema-version` is
  required, so the console script cannot be run as a person would run it. A
  defensible design for a supervised unit and a surprise in `[project.scripts]`.

`shepherd`, `shepherd-controld` and `shepherd-sessiond` all install and run;
`shepherd-controld` binds, serves and stops cleanly from the installed artefact.

---

## Things found **false of the tree** (or of the plan)

1. **S6's premise is false.** The plan says *"`MasterRuntime.resume()` **has no
   caller in `src/`**"*, repeating the router's "no caller" register (§T27-6).
   Measured: `daemons/plane.py::build_master` reads `MASTER_SESSION_KEY` back
   out of `app_state` and calls `runtime.resume(conversation)`. D10's continuity
   is **wired**. S6 was rewritten to assert the chain end to end — including the
   property a wired-but-wrong reader would get wrong (it resumes *exactly* the
   persisted id, not a freshly minted one) and the cold-start branch (a missing
   or non-string row resumes nothing, never `""`).
2. **§11 does not state the attribution at level 3.** S1's independent reading of
   §11's table — written from the spec rather than from `decide()` — disagreed
   with the shipped `TABLE` on exactly two cells, `local_destructive/3/human` and
   `external/3/human`, which the build attributes to `CLAIMED_HUMAN` rather than
   `POLICY`. **The build is right**: a record cannot tell the two cases apart
   afterwards and `CLAIMED_HUMAN` claims *less*. But §11's table has two columns
   saying only `allow`/`ask` and says nothing about *who* an allowance is
   attributed to, so the rule lives only in `policy.py`'s own comments. Recorded
   rather than absorbed, in `expected_for`'s docstring.
3. **`seed_fleet` cannot be called twice.** It numbers sessions from zero
   (`engine-session-0000`), so a second call re-uses ids it already wrote:
   measured, seeding 1 then 4 more yields **4** sessions, not 5. S5 therefore
   builds four independent fleets from the one builder rather than growing one
   cumulatively.
4. **A child's stdout is block-buffered on a pipe**, so `controld`'s one-line
   readiness banner never arrives until the process exits. The first version of
   S8's fixture hung until the suite timeout. Fixed with `-u` plus
   `PYTHONUNBUFFERED=1`; the banner then arrives in ~1.1 s. Also: `readline()`
   carries no deadline of its own, so the bounded wait had to move onto a reader
   thread — a `while time.monotonic() < deadline` loop around a blocking read
   consults its deadline only between reads that never return.

---

## The measurements

### S1 — the gate that can say no

Production's default is `AutonomyLevel.LEVEL_2` (`tools_master.DEFAULT_AUTONOMY_LEVEL`,
*"a misconfiguration must not read as a licence"*). `install_test_chokepoint`
defaults to `LEVEL_3`. **The deterministic suite was proving the level
production does not run at**, which is the plan's headline gap and is now
asserted so it cannot close by accident.

| measured on the composed registry | |
|---|---|
| registered tools | **35** |
| full-combinatorial cells (tool × level × own audiences) | **118** |
| cells that can raise a card | **2** |
| which | `interrupt_session`/`master`, `kill_session`/`master`, both at `LEVEL_2` |
| blast classes | 16 `local_read`, 9 `local_write`, 10 `local_destructive`, **0 `external`** |
| §11 `ask` rows reachable from any registered tool | **1 of 4** |
| unreachable | `external/2/master`, `external/2/session`, `local_destructive/2/session` |

So three quarters of §11's gate is unreachable from this build's registry, and
the whole of the product's "a gate that can say no" surface is two cells. That is
recorded as a measurement, not a requirement — `test_the_reachable_ask_rows_of_
the_spec_table_are_measured` asserts each unreachable row is unreachable *for the
reason the registry gives*, so a future `external` tool cannot leave the check
silently measuring the old shape.

### S5 — projection bounds

Both projections, at four fleet sizes, through the shipped `invoke()`:

| sessions | `fleet_summary` B | pretty lines | `fleet_tree` B | `needs_you` rows |
|---|---|---|---|---|
| 1 | 1 699 | **85** | 870 | 1 |
| 5 | 1 928 | **92** | 3 958 | 2 |
| 25 | 3 076 | **127** | 18 107 | 7 |
| 200 | 12 930 | **428** | 139 877 | 50 |

Both grow strictly; neither is bounded. §11's *"~40 lines regardless of fleet
size"* — about `fleet_summary`, per the M4 verifier's correction — is **already
over at one session** (85 lines, twice the budget) and at ten times it by 200.
The unbounded term is `needs_you`, and it is never truncated: the row count
equals the store's own `needs_you` population at every size, so no silent cap is
hiding inside the growth. The control is `anomalies`, a fixed dict, asserted
unchanged between the smallest and largest fleets.

G-M4-8 is a design decision and this pass does not close it. What it adds is the
curve the decision needs: one point cannot tell a constant projection from a
linear one.

---

## The mutation ledger

Technique, once, for all of it. Every mutation landed in a **per-task shadow**
(`scratchpad/qa-harness/shadow/`, with `src/`, `tests/`, **`docs/`** and
`pyproject.toml` copied, pytest run with `cwd=` the shadow) per RD-T19-7.
`docs/` is in the copy set because a dozen shipped tests read probe captures at
import. `__pycache__` is cleared before every run and each patch sleeps past the
second boundary (CLAUDE.md rule 4). **No mutation is a signal, a `kill`, a
subprocess, a socket, a teardown verb or any reboot-capable call, in any tree.**
The driver digests live `src/`, `tests/` and `pyproject.toml` before and after
every sweep and prints the comparison: `LIVE src UNTOUCHED: True`,
`LIVE tests UNTOUCHED: True`, `LIVE pyproject.toml UNTOUCHED: True` on every run
below. Driver: `scratchpad/qa-harness/mutate.py`.

**12 mutations: 12 RED, 0 unintended survivors, 1 intended survivor.**

| id | scenario | mutation | failing line |
|---|---|---|---|
| MUT-1 | S1 | §11's table allows `local_destructive/2/master` instead of asking | `assert ['local_destr…se by=policy'] == []` |
| MUT-2 | S1 | the card is raised correctly and the handler runs anyway | `assert ['interrupt_s…re=None', …] == []` |
| MUT-3 | S1 | a denied call is audited as an `allow` | `assert ["interrupt_s… result='ok'"] == []` |
| MUT-4 | S2 | `SPAWN_ORIGIN` becomes `ORCHESTRATOR` — D1's gap closes | `spawn_session and wake_candidates now agree on an origin` |
| MUT-5 | S2 | the wake stamp becomes conditional on a non-empty drain (E-M4-18) | `assert None == '2026-09-18T12:00:00Z'` |
| MUT-6 | S3 | reads stop being audited in a **composed** process | `assert ['s3-get_sess…written', …] == []` |
| MUT-7 | S4 | §12's forbidden generic text reaches the rail | `assert {'session needs attention'} == {'permission …sh(git push)'}` |
| MUT-8 | S5 | `needs_you` silently truncated to 10 | `assert ['200 session…t truncation'] == []` |
| MUT-9 | S6 | the reader resumes a plausible id that names no transcript (E-M4-8) | `the new runtime resumed ['turn-after-the-restart'], not …'s6-conversation-b0a1c2d3'` |
| MUT-10 | S7 | clause 20's release is dropped from `shut_down` | `the foreign worker was never released` |
| MUT-11 | S8 | `status` exits `0` while printing a refusal | `` `shepherd status` exited 0 beside a running daemon `` |
| MUT-12 | S9 | a console script names a callable that does not exist | `['shepherd: d…i/main.py)\n'] == []` |
| **BAD-MUT-1** | control | `WAKE_HEADER`'s em dash becomes a hyphen | **SURVIVED, intended** — S2 reads the constant and never respells it |

**MUT-10 was re-cut once.** Its first form deleted the `withdrawn = …`
assignment and produced a `NameError` — a broken harness, not a behavioural red.
Re-cut to `withdrawn = 0`, it is red at the assertion that matters.

**MUT-11 and MUT-12 were run at narrow scope, deliberately.** Gate A digests
every byte of `web/` and `cli/`, so a mutation of either is red by digest
regardless of behaviour; a ledger run at whole-suite scope could not have told a
behavioural red from a byte red. MUT-11 touches `cli/commands.py` and MUT-12
touches `pyproject.toml`, and both ran against their own scenario's module only.

---

## Scenario by scenario

| # | built | drives | observes | what a lying implementation would look like that it now catches |
|---|---|---|---|---|
| **S1** | yes, 14 tests | every registered `ToolDef` × both `AutonomyLevel` members × each audience in its own set, through shipped `invoke()` + shipped `build_authorizer`; both card outcomes | card raised / not; handler call count **while still blocked**; `decision`/`result`/`approved_by`/`approval_id`/`actor_kind`/`blast_class`; typed `Failure.REFUSED` and `DENIED_TEXT` | raises the card and runs the handler anyway; allows at `LEVEL_2` because tests only ever asked at `LEVEL_3`; audits a denial as an allow; denies by raising rather than answering |
| **S2** | yes, 7 tests | `invoke("spawn_session")` as `MASTER` over a `ScriptedRunner`; M2's `handle_stop` over a real capture; `wake.drain`; `TurnDriver` | the spawn's own returned id at every step; the row's origin; the drain; the stamp; the second drain; the prompt the runtime was handed | a wake set built from a fixture rather than from the session the master spawned; a drain that stamps twice or only on a non-empty set; a second drain that repeats rows |
| **S3** | yes, 5 tests | `get_session_output`/`terminal_snapshot` at both levels, as every declared audience, composed; then the same reads with **no** chokepoint | one audit record per call on disk, through the single reader; no card pending at either level; no record at all in the uncomposed process | audits reads only when a chokepoint happens to be installed by a test |
| **S4** | yes, 4 tests | M2's own `fold(NEEDS_INPUT)` and an M3 owned session into one projection; a real card raised through the gate | each row's own ask, as a set; the projection's key set, derived from `project_needs_you`; empty vs. absent; the approval's absence | a rail row whose ask is a category; a count that is not the row count; an empty rail indistinguishable from an unread one |
| **S5** | yes, 4 tests | T23's `seed_fleet` at 1/5/25/200, both projections through `invoke()` | wire bytes, pretty lines, `needs_you` row count vs. the store's own population, a fixed control term | a cap applied silently, with no counted truncation; a bound on one projection and not the other |
| **S6** | yes, 8 tests | `TurnDriver` writing the id; `plane.build_master` reading it back; a restart over one store; a cold start; a non-string row | the persisted value; the exact id resumed; `resume`'s single-caller set by AST with an inert negative-control fixture | a reader that resumes a freshly minted id; one that resumes `""` on a cold start; a writer that takes the last event's id; the register row silently reopening |
| **S7** | yes, 3 tests | the composed process, a master turn parked on a card, a **foreign** worker parked on a second, then shipped `shut_down((), …)` — five times | released or not; the release instant against `deadline_at`; which branch, counted separately | laundering a raise into a refusal; "freeing" a worker by letting its 600 s deadline expire |
| **S8** | yes, 7 tests (live) | a real `controld` on a free port, gated on its own banner; a real separate `shepherd status`; the same command with no daemon at all | exit code and both streams verbatim; the daemon still serving afterwards; nothing written outside the throwaway | a `status` answering from a stale in-process registry; one exiting `0` while printing an unknown; one reporting `0 sessions` (a silence read as good news) |
| **S9** | yes, 11 tests (live) | `python -m venv` + `pip install -e .` into a throwaway outside the repo; every name in `[project.scripts]`, enumerated from the manifest | each script exists, is executable, resolves its entry point without a traceback; exit codes against shipped constants; the daemon binds and stops; `EXIT_REFUSED` on a held port | an entry point naming a callable that does not exist; a package importable only from a source tree; a command reporting success while printing a refusal |

### Notes on scenario scope

* **S1's one substitution, named as a risk.** The handlers in the matrix are
  stand-ins that count and return a literal: the shipped handlers cannot be
  driven 118 times in the default lane (`spawn_session` starts a tmux pane,
  `install_hooks` writes a settings file). It is sound because `invoke()` reads
  `name`/`audiences`/`input_schema`/`blast_class` and hands the handler nothing,
  and it is **asserted** sound —
  `test_the_stand_ins_differ_from_the_shipped_tools_in_exactly_one_field`
  compares every `dataclasses.field` of `ToolDef` enumerated at test time. The
  control is `test_the_shipped_handler_meets_the_same_gate`, which denies a
  **real, unsubstituted** destructive handler through the real
  `compose_tool_surface` at `LEVEL_2`.
* **S1's gate is the shipped fixture's own body.** `tests/qa/_gate.py` is
  `install_test_chokepoint` with the `ApprovalStore` kept, because that fixture
  builds its store inside itself and a caller at `LEVEL_2` cannot answer a card
  it cannot reach. `test_this_packages_gate_agrees_with_the_shipped_fixture`
  drives one call through both and compares the audit records, so *"same gate"*
  is an observation.
* **S2 does not use `compose_tool_surface`**, and that is a deliberate scope
  limit: the composition builds a `LocalRunner` whose exec site is real `tmux`,
  so a composed spawn would start a real pane on this host. The `Runner` seam is
  what `ScriptedRunner` exists for; everything above it is shipped.
* **S4 is deterministic only.** This host has no browser, so every assertion is
  against the projection and never against the render, exactly as the plan
  requires.

---

## Test-side edits made, and why

**No product code was edited.** Two test-side changes were needed:

1. **`tests/boundaries/test_one_definition_site.py`** — `tests/qa/test_s6_
   restart_continuity.py` added to `DECLARED_SCANNER_MODULES`. S6's
   `modules_that_call_resume` is a module-level source-reading rule, so the
   shipped inventory check caught it *before the module had a single assertion
   in it* — the same way it caught its own author during the QA-prep pass. The
   entry carries its reason: it is the same shape as `test_master_turn.py`'s
   `modules_that_call_send` (P-M4-21) and deliberately not shared with it,
   because they answer about different members.
2. **`tests/qa/conftest.py`** — the `IdleMaster` double's `send` and
   `capabilities` were widened to `object` in the first draft, and
   `tests/e2e/test_live_lane_typechecks.py` caught it (that module is the
   `conftest.py` beside a live-marked test, so it is type-checked). Fixed by
   spelling the seam's own signatures. A double that does not satisfy the
   Protocol it stands in for can drift away from the seam unnoticed.

New inert fixture: `tests/qa/fixtures/a_second_resume_caller.py` — read as text,
never imported, module body performs no call at all (CLAUDE.md rule 1).

---

## Observations that are not findings

* **One live-lane transient.** The first full `pytest -m live` run failed
  `tests/e2e/test_live_owned_session.py::test_a_real_stop_carries_an_exit_code`.
  It passed in isolation immediately afterwards (1 passed in 2.75 s) and the
  full live lane then passed twice (75 passed, 89.9 s and again). Recorded
  unexplained rather than explained away. The test drives a real `claude` TUI
  through a trust dialog and reads tmux's pane-reaping, with ceilings its own
  docstring says were tuned against a measured 0.3 s / 4 s window — so it is
  inherently load-sensitive, and S9 adds ~20 s of venv-plus-pip work to that
  lane. If it recurs, giving S8/S9 their own lane is the cheap next move.
* **A scratch probe of mine touched the operator's real data dir.** While
  working out how to drive `shepherd-controld`, one unisolated run opened
  `~/.local/share/shepherd/shepherd.db` and created `/run/user/0/shepherd/`.
  Nothing was deleted; the daemon migrated and ran a discovery scan. It is why
  `test_the_daemon_wrote_only_into_the_throwaway_home` exists as a check rather
  than as a promise, and why both live modules scrub `XDG_*` and
  `CLAUDE_CONFIG_DIR` before starting anything.
* **An editable install writes into the source tree.** `pip install -e .`
  produces `src/shepherd.egg-info/` beside the package, not only inside the
  venv. It is gitignored and no boundary rule reads it, but it is a file S9
  created in the repo, so S9's teardown removes it — and only when that run is
  what created it. Verified: after `pytest tests/qa/test_s9_install_path.py -m
  live`, `src/shepherd.egg-info` does not exist.
* **Not attempted:** driving the rail's *render* (no browser on this host, and
  the plan forbids it); a composed `spawn_session` against real tmux; the
  installed wheel's package-data, which `tests/test_packaging.py` already builds
  and lists.
