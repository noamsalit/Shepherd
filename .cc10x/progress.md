# Progress

## Current Workflow

**M1–M4 are built, verified and QA'd.** There is no workflow in flight.

**2026-09-21 — documentation and design only.** Nothing under `src/` changed; the one change
under `tests/` is recorded below. A dark-mode UI redesign was worked through as a clickable
prototype rather than as code (`docs/design/ui-decisions.md`), and eight new decisions D57–D64
were added to the spec describing work that is **not built**.

**Start here for what to do next:** `docs/backlog/2026-09-21-projects-work-sources-and-ui.md`
is the consolidated forward-work register.

Closed the same day: **bring your own harness**, decided in outline and deferred
(`docs/specs/harness-contract.md`, six open questions in its §4); **credentials and
authentication**, recorded as four open questions the owner explicitly did **not** sign off on
(`docs/specs/credentials-and-auth.md`); and **real sandboxing**, recorded in spec §17 with the
honest statement that none exists today.

## Tasks

None open. The four milestones ran as four plan → implementation cycles, each with its own plan
and its own `*-BLOCKERS.md` ledger under `docs/plans/`. 86 tasks across the four, all closed.

The next body of work has a register but no plan yet: see W1–W5 in
`docs/backlog/2026-09-21-projects-work-sources-and-ui.md`. **W1 (the Projects backend) should be
routed as PLAN, not BUILD** — migration 004, a schema change from an FK to a join table, five
gated verbs, and a policy change both discovery lanes hit.

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

2026-09-21 — M1–M4 complete; documentation realigned for repository recreation.
