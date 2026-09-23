# Progress

## Current Workflow

**None in flight.** `wf-20260921T212808Z-9172ed6b` (PLAN → BUILD → QA) is closed.

**The Projects backend and the dark UI shipped 2026-09-22** — D57–D61 plus the six-page shell,
`flock.js` / `projects.js` / `settings.js`, and D65/D66/D67 resolving the rail and the session
view. Plan: `docs/plans/2026-09-21-projects-and-ui-plan.md` (executed at revision 5, acceptance
surface corrected to revision 7). Ledgers: `docs/plans/projects-ui-blockers/`.

**QA round 5 ran the full seven-link route** and returned **BLOCKED** on the day; the two findings
that caused it are now closed. Harness `tests/qa5/` — 22 files, 6,974 lines, 35 scenarios over six
waves, mutation floor 11/11. Post-fix the harness runs **36 PASS / 0 FAIL / 1 PARTIAL**, stable
across three consecutive runs with the edit-dialog retry never needed (1 press each).

- **BC-1 — fixed** (`7487f1a`, `b24d46a`). *Last-resolver-wins*: an async read wrote shared view
  state and painted without checking its write was still wanted, so a slow read for A repainted
  under B. Both fixes make the intent (`view.openId`, `view.openSessionId`) a synchronous write the
  continuation re-checks. Reproduced deterministically with a page-level `fetch` shim that parks one
  read and releases it after a newer one has painted.
- **BC-2 — open, low, no oracle.** `#stream-status` still reads `live` 30 s after the daemon stops.

**The round's real yield was the harness, not the product.** Eleven defects were found *inside* the
instrument built to report defects — including a run report that could not express a failure at all
(140 artifacts, `FAIL` total 0, 47 all-green with `scenarios: 0`), a `"kill-server" in argv`
membership test that tmux defeats by prefix resolution, and a hard-coded `760` inside the probe
written to catch hard-coded widths. That is this repo's dominant defect class recurring one level
up, and it is the reason the round was worth running.

**Recorded, unassigned:** DUP-2 (`loadList()`'s unconditional `renderDetail()` rebuilds `#proj-edit`
under an in-flight click); `loadDraftPaths()` at `projects.js:592` can show project A's repo paths
in project B's Edit dialog (unreproduced); SI-1 (C-8 viewport parametrisation — 34 retirement
entries, 102 node ids, needs its own BUILD); AC-28's live-render clause undischarged.

## Tasks

None open. The four milestones ran as four plan → implementation cycles, each with its own plan
and its own `*-BLOCKERS.md` ledger under `docs/plans/`. 86 tasks across the four, all closed.

**W1 and W4 are done.** Routing W1 as PLAN rather than BUILD was the right call: the plan-review
gate ran two fresh passes returning 7 and 5 blocking findings, and the QA round that followed found
three of the plan's own acceptance criteria had gone stale against the tree.

The next body of work has a register but no plan: **W2** (discovery switches, D62), **W3** (work
sources, D63/D64) and **W5** in `docs/backlog/2026-09-21-projects-work-sources-and-ui.md`. W6's
documentation debt is the cheapest thing on the list, and item 6 — Appendix A — is now unblocked,
because migration 004 removed the `root_path` it was waiting on.

## Completed

**M1 — foundation + visibility.** 20/20 tasks. Both daemons, the hook dispatcher, ingest folding
into `session` columns, a minimal `toolsurface/`, four of six tables plus migrations,
workspace/repo discovery and binding, the fleet page, SSE. Hookless discovery proven live on the
owner's own machine. All three verification defects closed with negative controls.

**M2 — signals engine.** 19/19. The classifier over the transcript tail and stop metadata,
`next_actions[]`, the 7-bucket palette and its ordering, the Needs-You rail, `replay`, the
`unknown` rate. Milestone verification returned FAIL on 2 of 16 acceptance clauses; both were the
plan claiming proof it did not have, neither was an engine bug, and both were closed with the
check proven to bite.

**M3 — owned sessions.** 24/24. Verification: 12 PASS / 4 FAIL / 1 UNVERIFIED on 17 clauses, all
four closed. The real one: the `kill-server` guard was a **spelling**, and tmux resolves
`kill-serv`.

**M4 — orchestrator.** 23/23. Track C was cut on a security finding — a deviation from §16,
recorded with its reversal condition. Verification: 20 PASS / 1 FAIL on 21 clauses; the FAIL named
a file nobody built. Remediated.

**M1–M4 QA pass.** The first pass to test the four milestones **composed** rather than each one's
own seams. Five defects; two fixed, three recorded with reasons. The one that justified the pass:
**D31's wake set could never fill in production** — the query filtered on an origin nothing wrote,
and every wake test passed because each planted its own row.

**2026-09-20/21 — publish preparation.** Every employer-associated identifier removed from the
tree; the frozen-evidence override and its three standing conditions recorded in `CLAUDE.md`; the
macOS port merged onto a clean parentless root with the work identity rewritten out of every
commit; D56–D64 written; five new documents added.

**2026-09-22 — Projects backend + the dark UI (D57–D61, D65–D67).** Migration 004, seven
project verbs registered once as `ToolDef`s so the master and the HTTP API share them, `Unassigned`
as a reserved undeletable project, a delete that cascades and refuses rather than killing silently,
and the six-page shell. `upsert_workspace`'s match-on-name went with it, closing a live defect where
`/work/api` and `/personal/api` collapsed into one project.

**2026-09-23 — publish and cleanup.** `integration` fast-forwarded into `main` and deleted;
`origin` reduced to a single branch, byte-identical to local. Fourteen merged branches and their
agent worktrees removed (543 MB). A module-level `mkdtemp` in `tests/runner/test_local.py` was
found leaking one directory per collection — 1,516 had accumulated — and now cleans up at exit.

## Verification

**Current state, measured on Linux:** **1866 passed, 2 skipped, 75 deselected**; live lane **75
passed**; boundary rules **105**; `mypy --strict src` clean over **127** files with
`disallow_any_explicit` on; `daemons/controld.py` still **140** lines.

**One test repaired on 2026-09-21.**
`tests/engines/test_hook_dispatch_delivery.py::test_the_wedge_fixture_really_wedges_an_unbounded_writer`
passed on macOS and failed on Linux. Not flaky — a real platform difference: the test's 40 KB
`LARGE_FRAME` fits inside Linux's `/proc/sys/net/core/wmem_default` of **212,992** bytes, so the
write completed into the socket buffer and the writer never wedged. macOS's default is ~8 KB. The
negative control now uses its own 1 MB `WEDGE_FRAME`, sized clear of both platforms rather than
probed — a test that reads the tunable it depends on can be made to pass by changing the machine.

**Standing:** every ledger records survivors, bad mutations, and "what this did not prove" as
named sections, so a later reader inherits the doubt as well as the result.

## Historical — M3 Task 10, `engines/claude_code/spawn.py` (2026-09-17)

`claude --version` at the time: **2.1.273 (Claude Code)** — `data-schemas.md` pins every shape to
2.1.270 (G-M3-7). M3 T1 later recorded the engine self-updating mid-task to **2.1.274**
(`2026-09-17-m3-BLOCKERS.md`, BLOCKER-T1-1), which is the point: the version moves under you.
`tmux -V`: 3.4. The six flags M3 spawns with:

```text
 --effort <level>                Effort level for the current session
 --fork-session                  When resuming, create a new session ID
 --model <model>                 Model for the current session. Provide
 -n, --name <name>               Set a display name for this session
 --no-session-persistence        Disable session persistence - sessions
 --session-id <uuid>             Use a specific session ID for the
```

No flag has drifted. `tests/engines/test_spawn_argv.py::test_every_flag_is_present_in_claude_help`
(`-m live`) asserts this on every live run and prints the version it saw.

## Historical — pre-M1 groundwork (2026-09-12)

- Read `docs/specs/orchestrator-platform.md` in full.
- Established environment ground truth (Python/SQLite/tmux/claude/network/no-node).
- Recovered and analysed the §18 hook-payload probe from a prior session.
- `FULL OUTER JOIN` probe (spec §18): SQLite 3.45.1 — **SUPPORTED**.
- Hook-event probe: 77 real events captured across 12 event types; 12 registered event types
  never fired. Later grown to the 429-event corpus under `docs/probes/2026-09-14-schemas/`.

## Last Updated

2026-09-23
