# Forward work — projects, work sources, and the UI redesign

**Written 2026-09-21. Updated 2026-09-23.** This is the register for everything
decided on 2026-09-21 that was **not built** at the time.

**W1 and W4 have since been built** — the Projects backend (D57–D61) and the dark
UI — and are marked DONE below with the record kept rather than deleted, so the
register still reads as the account of what was decided and when it landed.
**W2, W3 and W5 are untouched**, and W6's documentation debt is partly discharged.

| | status |
|---|---|
| W0 — Linux-only test failure | **DONE** 2026-09-21 |
| W1 — Projects backend (D57–D61) | **DONE** 2026-09-22 — `docs/plans/2026-09-21-projects-and-ui-plan.md` |
| W2 — Discovery switches (D62) | open |
| W3 — Work sources (D63, D64) | open |
| W4 — The UI | **DONE** 2026-09-22, with D65/D66/D67 resolving the open questions |
| W5 — Not started | open |
| W6 — Documentation debt | items 1–5 and 7 open; item 6 (Appendix A) **unblocked** — migration 004 has landed |
| W7 — Test-suite health | W7.3 **DONE**; W7.1 (order-dependent suite) and W7.2 (qa5 in the default lane) open |

---

## Where the decisions live

| | |
|---|---|
| **D57–D64** | `docs/specs/orchestrator-platform.md` §3 — projects, lifecycle, `Unassigned`, repo↔project many-to-many, delete semantics, discovery switches, work sources, provider-declared filters |
| **UI** | `docs/design/ui-decisions.md` — U1–U15, plus the two artifact links |
| **Harness** | `docs/specs/harness-contract.md` — deferred, decided in outline, six open questions |
| **Auth** | `docs/specs/credentials-and-auth.md` — four questions, **none answered** |
| **Sandboxing** | spec §17 — none exists today; the container plan is recorded there |

## W0 — done on 2026-09-21

- **The Linux-only test failure is fixed.** `tests/engines/test_hook_dispatch_delivery.py::test_the_wedge_fixture_really_wedges_an_unbounded_writer`
  asserted that an unbounded writer wedges against a hung peer. It passed on
  macOS and failed on Linux for a real reason: `LARGE_FRAME` is 40 KB and
  Linux's `/proc/sys/net/core/wmem_default` is **212,992**, so the write landed
  entirely in the socket buffer and returned. macOS's default is ~8 KB, so
  there it wedged. The negative control now uses its own `WEDGE_FRAME` of 1 MB,
  sized clear of both rather than probed — a test that reads the tunable it
  depends on can be made to pass by changing the machine.

## W1 — Projects backend (D57–D61) — **DONE 2026-09-22**

Executed as `docs/plans/2026-09-21-projects-and-ui-plan.md` revision 5, with the
acceptance surface corrected to revision 7 after QA round 5. All seven items
below shipped; `list_repos` gained both a tool and a route, and the verbs became
**seven** rather than five (`list_projects` and `list_repos` joined the
lifecycle five). The original text is kept below as the record of what was asked
for.

The largest piece, and **not a UI change**. It can land without touching
`web/static/` at all, which keeps the D38 byte-freeze out of it entirely.

1. **Migration 004** — `workspace.root_path` dropped; `workspace.description`
   added; `repo.workspace_id` replaced by a repo↔project join table (D60).
2. **`admission.py`** — the allowlist becomes the registered repo paths alone.
   Drop the workspace-root branch (and with it the T11-1 special case).
3. **`upsert_workspace`'s match-on-name goes.** Identity is `workspace.id`.
   This closes a live defect: today `/work/api` and `/personal/api` collapse
   into one project and the second silently overwrites the first's path.
4. **Five verbs**, registered as `ToolDef`s so the master and the HTTP API share
   them: `create_project`, `rename_project`, `delete_project`, `add_repo`,
   `remove_repo`. `create_project`, `add_repo` and `delete_project` are
   `blast_class=local_destructive`.
5. **`list_repos` gets a tool and a route.** It exists in the store today and
   nothing exposes it, so the UI cannot see a project's repos at all.
6. **`Unassigned`** (D59) — a reserved project, and the policy lives in
   `bind_cwd_to_repo`, the one function both discovery lanes already call.
7. **Delete** (D61) forgets, cascading to sessions; running sessions force a
   three-way choice rather than being killed silently.

**Route it through cc10x as PLAN first, not BUILD.** Migration plus a schema
change plus five gated verbs plus a policy change both discovery lanes hit is
exactly the scope where the plan-review gate earns its keep.

## W2 — Discovery switches (D62)

Three independent gates, all shipping **on**:

1. `discovery_pass` **inside** `run_discovery_loop` — not the thread. The
   thread also owns the liveness sweep and M3's mailbox pass, so killing it
   silently loses the demotion that stops a wedged session claiming `running`.
2. D47's accept-the-first-event-of-any-kind, which is what makes the hook lane
   a second discovery source.
3. `bind_cwd_to_repo`'s auto-create, which is D59's policy.

**One sub-question is deliberately open:** with (2) off, a hook event from an
unregistered session must either be **dropped** — losing the stop reason for a
session the scan is showing — or **accepted without registering**, which means
holding state for a session we decided not to track. Neither is free. Answer it
when a switch is actually needed.

## W3 — Work sources (D63, D64)

Arrives with M5's `queue` table, or earlier as configuration-only.

1. Queue configuration moves **onto the project**; Settings keeps health
   (`last_sync_at`, `last_sync_error`, drain state).
2. `WorkItemCapabilities` gains a **filter declaration** — per field: key,
   label, kind (`single_select` / `multi_select` / `text`), and how options are
   fetched. The UI renders the declaration and never learns a query language.
3. The raw provider query stays as an explicit **Advanced** field.
4. **Saving validates and reports the match count.** A typo returning zero is
   otherwise indistinguishable from a correct filter over an empty backlog —
   neither is an error, nobody is told, and the queue quietly does nothing.
5. `queue.enabled` stays `FALSE` by default. *Connected but paused* is a normal
   state the page renders plainly, not a warning.

## W4 — The UI — **DONE 2026-09-22**

The open questions this section names were answered before implementation:
**U1–U4 and U15** were resolved in `docs/design/ui-decisions.md`, and the two
that mattered most were settled as spec decisions rather than UI notes — the
autonomy toggle is Settings-only (**D65**), and the Needs-You rail leaves the
shell entirely (**D66**), with the session view relocating into the Flock's
third pane (**D67**). The projection behind the rail was **not** retired; only
its renderer went.

The original text is kept below as the record of what was open.

Blocked on nothing technical; the owner gates it. See
`docs/design/ui-decisions.md` for the settled list and, more importantly, for
**U1–U4 and U15, which must be answered before implementing.** The two that
matter most:

- the **Needs-You rail** has no home in the new design, and it is the element
  the whole product is built around;
- the **autonomy toggle** is Settings-only, against §12's *"visible at all
  times"*.

## W5 — Not started, ordered by when they bite

- **Queues and Kanban pages** — placeholders in the design, never discussed.
- **Model and engine per session (U15)** — proposed three-level precedence, not
  decided.
- **Bring your own harness** — `harness-contract.md`, six open questions.
- **Credentials** — `credentials-and-auth.md`, four open questions, none
  answered. Needed only when Shepherd stops being one person on one machine.
- **Real sandboxing** — spec §17. Same trigger as credentials.


## W6 — Documentation debt found by the 2026-09-21 audit

Two read-only audits compared every factual claim in the specs against `src/`. Most
findings were corrected the same day; these were left, deliberately, because each is a
section rewrite rather than a sentence fix. **Each is a real inaccuracy, not a nitpick.**

1. **§6's `Runner` Protocol lists 8 members; `runner/base.py` ships 12** — the eight plus
   `pane()`, `list_owned_panes()`, `attached_clients()`, `clear_input()`. `snapshot()`'s
   second parameter is `scrollback`, not `lines`. A status comment now says so in §6;
   the member list itself was not rewritten.
2. **§7 omits ten shipped columns.** `session` carries `observed_at`,
   `live_subagent_ids`, `created_task_ids`, `completed_task_ids`, `pid`, `proc_start`,
   `auto_compact_at`, `quota_notice_at`; `repo` carries `owner_id` and `git_common_dir`.
   `git_common_dir` matters most — it is D48's binding key and §7 points at `root_path`
   instead.
3. **§16's M4 row still says "the two MCP exporters".** One shipped. §11 now carries the
   correction; §16 does not.
4. **§14 names `ScriptedWorkItemProvider` and `ScriptedEngine`**, which do not exist, and
   omits `ScriptedHost`, which does. Flagged in place, list not rewritten.
5. **§8's hook-dispatcher code sample is the shape that was rejected.** Flagged in place;
   the real one-liner lives in §15 and in `hookd_command.py`.
6. **Appendix A needs a rewrite** (C22): `repo_id` values contradict D48, and the
   `workspace` row is built on `root_path`, which D57 removes. **No longer blocked** —
   migration 004 landed on 2026-09-22 and `root_path` is gone, so the schema this
   appendix must be rewritten against is now settled. This is the oldest open
   documentation item in the tree: C22's *"when: before M1"* is unmet five
   milestones later.
7. **§12's ASCII mockups took damage in the 2026-09-20 scrub** — box borders at the
   fleet-page mockup no longer align after the substitutions changed string widths.

**Method note, worth keeping.** Both audits were told to *verify every numeric and
symbolic claim against the source* rather than to read for plausibility. That is what
found them: the counts a reader trusts most (105 boundary rules, 127 mypy files, 140
lines, 20 stop reasons, 64 decisions) were all **correct**, and the errors were in prose
that looked settled.

## W7 — Test-suite health, found by the 2026-09-23 cleanup

Two findings, both about the **default lane** rather than about any product code.

### W7.1 — the default run is order-dependent, and can fail ~100 tests

A plain `.venv/bin/pytest` on `9bfb87e` produced roughly **100 failures and errors** across
`tests/web/`, `tests/tools/test_render_check_args.py` and
`tests/testkit/test_scripted_master.py`. Every one carried one of two messages:

- `playwright._impl._errors.Error: It looks like you are using Playwright Sync API inside the
  asyncio loop.`
- `asyncio.run() cannot be called when another asyncio event loop is running in the same thread.`

Both say the same thing: **some earlier test leaves a running event loop in the main thread**,
and every later test that needs the main thread free then fails. `pytest-randomly` is installed,
so which tests land downstream of the leak changes per run — the suite is green or badly red
depending on ordering. That is why it has not been noticed: it is not flaky in the usual sense,
it is *positional*.

**Measured, deterministically.** `.venv/bin/pytest -p no:randomly` on `9bfb87e`:

```
39 failed, 2185 passed, 2 skipped, 76 deselected, 9 warnings, 60 errors in 322.77s
```

The 60 errors are all *at setup* — the browser fixture never comes up — and they are confined to
`tests/web/test_decision_live.py`, `test_projects_page.py`, `test_settings_live.py`,
`test_shell_live.py` and `test_terminal_fit_live.py`. Files immediately around them
(`test_chat_page.py`, `test_flock_page.py`, `test_projects_stream.py`, `test_routes*.py`) pass.

**The clue worth chasing first.** pytest's `unraisableexception` plugin surfaces this during the
first failing file:

```
RuntimeWarning: coroutine 'drain' was never awaited
```

`drain` is the helper in `tests/testkit/test_scripted_master.py` and
`tests/contracts/test_master_contract.py`, both of which call it through `asyncio.run(...)`. A
`drain(...)` coroutine is therefore being **constructed and abandoned**, and the warning only
surfaces later, when the garbage collector gets to it — inside whichever test happens to be
running. That is the shape of an `asyncio.run` that raised before awaiting, leaving its loop
behind. `tests/testkit/` runs at roughly 78% and the web failures begin at 86%, which fits.

**And it is worse than an ordering problem.** `tests/web/test_projects_page.py` run **on its
own** does not fail — it **hangs**, at 0% CPU with no output, still alive after eight minutes.
So "run the file by itself to check the product" is not available either, and no claim should be
made that these pages are fine on the strength of the suite. Whatever holds the loop may also be
holding a fixture open.

**Ruled out so far:** `tests/master/test_sdk_tools.py` and `tests/testkit/test_scripted_master.py`
are each clean when run immediately before `tests/tools/test_render_check_args.py`, so it is not
either module alone. There is no `new_event_loop`, `set_event_loop`, `run_forever` or
`get_event_loop` anywhere in `tests/`, `src/` or `tools/`. `anyio` is installed and its pytest
plugin auto-loads; there is no `pytest-asyncio` and no `asyncio_mode` setting.

**This is the reason the suite totals quoted in `README.md` and `HANDOFF.md` are marked as
measured under a named ordering rather than stated flat.** A count that depends on the shuffle
is not a count.

**One thing that is *not* a defect:** `tests/qa5/test_guards.py::test_sweep_removes_a_run_root_whose_pid_is_gone`
fails when a second pytest process is running, because it refuses to sweep a run root belonging
to a live pid. That is the guard doing its job. Never run two pytest processes at once here.

### W7.2 — `tests/qa5/` runs in the default lane, and nobody decided that

`testpaths = ["tests"]`, so the round-5 harness runs on a plain `pytest`: it starts a headless
Chromium and a tmux server on the throwaway `shepherd-qa` socket, and it takes the default run
from roughly two minutes to roughly **fourteen**. `addopts` excludes only `-m live`, which is
about real `claude` processes and does not cover this.

It fell out of committing the harness under `tests/`; it was never chosen. The trade-off is real
in both directions — the browser lane is what caught the last milestone's only product defect,
and it is also what makes the edit-test loop slow enough to discourage running it. Three options:
leave it, give it its own marker deselected in `addopts` exactly as `live` is, or move it out of
`testpaths`. **If it is ever deselected, `README.md` must say so** — that file currently implies
one command covers everything.

### W7.3 — a module-level `mkdtemp` was leaking a directory per run

**Fixed 2026-09-23.** `tests/runner/test_local.py` created `SINK_DIR` with `tempfile.mkdtemp`
at import and never removed it, leaking one directory into the system temp dir on **every
collection**; 1,516 had accumulated. It now registers an `atexit` cleanup. Proved by measuring
the directory count either side of a run: delta 0, where it had been +1. All 1,521 were swept the
same day, after checking that every file inside was the known 11-byte test sink.

**The wider sweep, for the record.** `/tmp` went from 2.2 GB to 286 MB: the repo's own pytest
basetemp `shp-0` (1.2 GB, nine run trees), pytest's default `pytest-of-root` (496 MB), scenario
S9's throwaway venv (281 MB), 44 generic `tmp*` fixture dirs, 12 stale chromium profiles, and
seven `*.orig.py` mutation-run backups of product source — those last checked against `HEAD`
first, because a backup that does **not** match a committed blob could have meant a mutation left
sitting in the tree. Four did not match; they are snapshots of files that have since changed, and
the working tree was clean, which is the assertion that settles it.

`shp-0` was **emptied rather than removed**: `tests/conftest.py` validates that it is owned by us
at mode `0700` before using it, and leaving the directory in place closes the window where an
unprivileged local user could pre-create it.

**`shp-0` is not leaking.** A suite run after the sweep left **zero** directories behind, so the
nine trees came from runs killed mid-flight — unlike the `shepherd-t8` leak above, which was real.

## Still open from before 2026-09-21

Carried forward so this file is a complete register. Detail in
`docs/plans/m4-blockers/router-decisions.md` and
`docs/plans/m1-m4-qa/fixes.md`.

1. **`fleet_summary` exceeds §11's "~40 lines regardless of fleet size"** —
   measured 92 lines at 5 sessions, 127 at 25, 428 at 200. Two viable repairs.
2. **`shepherd status` is blind to a running daemon** — needs a transport
   decision *and* a second Gate A re-base, which must be taken together.
3. **§T25-8** — a worker released at shutdown meets a closed store.
   **Deterministic, not racy**; the QA pass measured it 20/20.
4. **Track C's reversal condition** — every handler now receives a
   `CallerContext`, but `caller_id` is an **unauthenticated self-stamp**. Scope
   is expressible; identity is not.
5. **F6** — drop the systemd user-unit installer?
6. **License** — none chosen. Default copyright applies on a public repo.
7. **`MacHost` is unverified** (`verified() == False`). A macOS port landed on
   2026-09-20 and the suite passes there, but the five G1 captures the spec asks
   for are not in the tree.
8. **The browser UI has never been opened by a human.** Still true, and now a
   narrower gap than it was: QA round 5 drove all six pages through a real
   headless Chromium across 35 scenarios, so *rendering* is no longer unproven.
   What no automated run can settle is whether the pages are **usable** —
   HANDOFF's manual checklist stands, including the no-JavaScript degrade.
9. **Appendix A of the spec is stale** (C22) — see W6 item 6. Migration 004 has
   landed, so it is no longer blocked, only undone.
