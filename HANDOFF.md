# Shepherd — handoff

**Last updated 2026-09-23.** M1 through M4 are built, verified and QA'd, and so are the Projects
backend and the dark UI that sit on top of them. This file is what you need to take the project
anywhere, plus an honest list of what is **proved**, what is **recorded as unverified**, and what
is **still open**.

## State

| | |
|---|---|
| default suite | **2185 passed, 2 skipped, 76 deselected — and 39 failed, 60 errors.** Measured 2026-09-23 under `-p no:randomly`, because the run is order-dependent. Every failure is in the browser lane and none implicates product code; written up as **W7.1** in the forward-work register |
| live lane (`pytest -m live`) | **75 passed as last measured on 2026-09-21**, not re-run since — it starts real `claude` processes against your own config |
| boundary rules | **105 passed** |
| `mypy --strict src` | clean over **131** files, `disallow_any_explicit` on |
| composition root | `daemons/controld.py` still **140** lines, guard constants unedited |
| decisions | **68** (D1–D67, plus D38.1) in `docs/specs/orchestrator-platform.md` §3 |
| your settings file | `~/.claude/settings.json` sha256 `375e5322…d6ac` — **never written, checked on both sides of every live test**. Shepherd's hooks are **not installed**. |
| your tmux | socket `shepherd` never named in a write. The **socket** is the invariant; session *names* are not, and any check written against them goes red the next time you open a terminal. |

## Git state, as of 2026-09-23

The publish plan in earlier versions of this file — *"delete and recreate the remote from
`integration`"* — is **done**. There is now one branch, in one place, and nothing to reconcile.

- **`main`** `9bfb87e` — 112 commits, everything: M1–M4, the macOS port, the identifier scrub on a
  clean parentless root, the Projects backend and the UI redesign, and the QA harness that tested
  them. Author and committer `Noam Salit <nsalit@gmail.com>` throughout, with zero
  employer-identifier hits in every commit's tree rather than only at the tip.
- **`origin/main`** — byte-identical to local `main`. `origin` holds **no other branch**.

`origin` is `git@github.com:noamsalit/Shepherd.git`. The pre-scrub published history was replaced,
not rewritten in place.

**Local branches, cleaned up on 2026-09-23.** `integration` was fast-forwarded into `main` and
deleted. `clean-root` and the fourteen `worktree-agent-*`/`remfix4-lane-*` branches are gone: each
was fully merged, carrying no commit unreachable from `main`. Fourteen agent worktrees under
`.claude/worktrees/` were removed with them (543 MB).

**Three remain and are safe to force-delete**, each verified to carry nothing unique:

| branch | why it is redundant |
|---|---|
| `docs/publish-prep` `667b0c3` | the pre-scrub lineage (root `22d9ef2`). Shares **no merge-base** with `main`; every "mirror of integration" commit on it landed on `main`, and its tree is a net −11,193 lines against it |
| `macos-original` `dade568` | the macOS port as it arrived, before the identity rewrite. All five commits exist on `main` as re-authored copies — `1dc1713`, `769cdb3`, `09671c0`, `b601a8e`, `e82d86c` |
| `worktree-agent-ab6cfa80ec1636e6f` `41f9504` | T8.1 `read_decision`. `main` holds a strict superset of both files it touches |

Verified by comparing content, not by trusting subject lines. They survive only because the cc10x
git guard blocks `git branch -D` without an approval token.

**Backups.** `/root/shepherd-backup-20260920/` holds bundles and worktree tarballs from the publish
preparation, each verified by restoring it and comparing tree hashes rather than by checking the
file exists. `/root/shepherd-branch-archive-20260923.bundle` (5.7 MB, `git bundle verify` clean) is
a complete archive of every ref as it stood immediately before the branch cleanup above — so the
deletions are reversible even though nothing unique was in them.

## What changed on 2026-09-20 / 21

Documentation and design only, with two exceptions, both named. **Nothing under `src/` changed
except one comment line in `web/static/rail.js`** (part of the identifier scrub, commit `85000d5`),
and one test was repaired — see below. That repair exists on **`integration`**, not on
`docs/publish-prep`.

- Every employer-associated identifier was removed from the tree. The override that allowed editing
  frozen probe evidence, and its three standing conditions, are recorded in `CLAUDE.md`.
- **D56–D64** added. D56 fixes which seam a future engine class may arrive through. D57–D64 described
  work that was **not built at the time**: project lifecycle, `Unassigned`, repo↔project
  many-to-many, delete semantics, discovery switches, per-project work sources, provider-declared
  filters. **D57–D61 were built on 2026-09-22**; D62–D64 are still unbuilt — see the next section.
- New documents: `docs/specs/logical-architecture.md`, `docs/specs/harness-contract.md`,
  `docs/specs/credentials-and-auth.md`, `docs/design/ui-decisions.md`,
  `docs/backlog/2026-09-21-projects-work-sources-and-ui.md`.
- **A dark-mode UI redesign**, at that point a clickable prototype and not code:
  https://claude.ai/artifact/1HFNab8sksQdz7WAP4SfFc — with the pre-redesign UI rebuilt beside it at
  https://claude.ai/artifact/JMSzca6pWM38GHuFVmNQeE. Decisions in `docs/design/ui-decisions.md`.
  No file under `src/shepherd/web/` had been changed **yet**; that happened on 2026-09-22.
- **One test repaired** (`tests/engines/test_hook_dispatch_delivery.py`): a negative control passed on
  macOS and failed on Linux because its 40 KB frame fits inside Linux's 212,992-byte socket send
  buffer and so never wedged. It now uses a 1 MB frame, sized clear of both platforms.

## What changed on 2026-09-22 / 23 — the Projects backend and the UI

This is the first body of work since M4, and the first that touched `web/static/` at all. Plan:
`docs/plans/2026-09-21-projects-and-ui-plan.md` (revision 7), design:
`docs/plans/2026-09-21-projects-and-ui-design.md`, ledgers: `docs/plans/projects-ui-blockers/`.

**Built — D57–D61, the Projects backend:**

- **Migration 004** (`store/migrations/004_projects.sql`) — `workspace.root_path` dropped,
  `workspace.description` added, `repo.workspace_id` replaced by a repo↔project join table (D60).
- **Seven verbs registered as `ToolDef`s**, so the master and the HTTP API share one implementation
  rather than two: `create_project`, `rename_project`, `delete_project`, `add_repo`, `remove_repo`,
  `list_projects`, `list_repos`. `web/routes.py` maps a path to a tool name.
- **`Unassigned`** (D59) — a reserved project that cannot be deleted, with the policy in
  `bind_cwd_to_repo`, the one function both discovery lanes call.
- **Delete cascades and refuses** (D61): a project with running sessions forces a three-way choice
  rather than being taken silently.
- **`upsert_workspace`'s match-on-name is gone.** That closed a live defect — `/work/api` and
  `/personal/api` collapsed into one project and the second silently overwrote the first.

**Built — the dark-only UI.** `web/static/` gained `flock.js`, `projects.js` and `settings.js`;
`app.css`, `app.js` and `index.html` were rewritten. The vocabulary changed in `core.stops.PALETTE`
and nowhere else: Herd → **Flock**, `unfinished` → **stranded**, `paused` → **limit exceeded**,
`unclassified` → **unknown**. **D66** takes the Needs-You rail off the shell and **D67** relocates
the session view into the Flock's third pane — a relocation, not a deletion: `session.js`,
`terminal.js` and the vendored `xterm.js` are retained and reachable.

**Not built, still:** D62 (discovery switches) and D63/D64 (work sources and provider-declared
filters). Those are §W2 and §W3 of the backlog register and are untouched.

**QA — five rounds, and the fifth ran the full route.** Rounds 1–4 raised 22 defects but none of
them ran the whole seven-link QA lane. Round 5 did, against a purpose-built harness
(`tests/qa5/`, 22 files, 35 scenarios over six waves). It found **one real product defect** and a
low-severity candidate, and — more usefully — **eleven defects inside the harness built to report
them**, including a run report that could not express a failure at all. The report is
`.cc10x/qa/wf-20260921T212808Z-9172ed6b/report.md`.

The product defect, fixed in `7487f1a` and `b24d46a`, is worth naming because it is a class rather
than an incident: **the pane belonged to the last read that resolved, not the last one asked for.**
An async read wrote shared view state and painted without checking that its write was still wanted,
so tapping B then A while A was slow left B's data under A's heading. Both fixes make the *intent*
(`view.openId`, `view.openSessionId`) a synchronous write that the async continuation re-checks.

**Start here for what to do next:** `docs/backlog/2026-09-21-projects-work-sources-and-ui.md` is the
consolidated forward-work register, including everything still open from before.

## Running it here

```
.venv/bin/pytest                    # the default lane
.venv/bin/pytest -m live            # real engines, real panes — opt-in, and it is why the marker exists
.venv/bin/mypy --strict src
```

The live lane is excluded from the default run **deliberately**: for three milestones a declared
marker did *not* deselect it, and a plain `pytest` was starting real `claude` subprocesses and reading
your real config. That cost an incident. The exclusion is in `addopts`, not only in a comment.

## Taking it to the Mac

**The macOS port landed on 2026-09-20** and the suite passes there; its commits are on `main`
(`1dc1713`, `769cdb3`, `09671c0`, `b601a8e`, `e82d86c`).
`MacHost` is still `verified() == False`, and the five G1 captures M1 asks for are **not in the tree** —
treat macOS as working-but-unattested rather than verified.

**Nothing is installed on this host** — the three console commands exist only as declarations, which
is why the QA pass drove a real `pip install -e .` into a throwaway venv (scenario S9). On the Mac:

```
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/shepherd doctor           # start here: it reports engine, schema, database, discovery
.venv/bin/shepherd status
.venv/bin/shepherd-controld --port 8787
```

Then open `http://127.0.0.1:8787/` — six page roots behind one nav: **Shepherd** (the
orchestrator chat, and the landing page), **Flock**, **Projects**, **Queues**, **Kanban**,
**Settings**. Queues and Kanban are placeholders. The redesign's renames are **in the code** as of
2026-09-22; `chat`/`fleet` survive only as the two nav element ids, deliberately, because frozen
assertions name them.

**Two rough edges on that path, both measured and both minor:** `shepherd --help` answers
`unknown command '--help'` (exit 64), and `shepherd-sessiond` with no arguments is an argparse error
because `--expected-schema-version` is required — deliberately, so a relay cannot start against a
schema it was not built for. Both are behind a byte-freeze on `cli/` that has spent its one permitted
re-base, so they are recorded rather than patched.

## What a human must check, because this host cannot

**This is a narrower gap than earlier versions of this file described.** There is now a headless
Chromium here, and `tests/qa5/` drives all six pages through it across 35 scenarios — so *the pages
render* is proved, and so is a good deal of their behaviour. What no automated run settles is
whether the result is **usable**, and that is what this list is for. On the Mac:

1. the conversation streams line by line when you send the master a message;
2. an approval card appears **and both buttons resolve it** — and it leaves both the sidebar and its
   inline position;
3. **Settings** shows the current autonomy level and changes it. It lives there and nowhere else now
   (**D65**); if you find that control on any other page, that is a defect;
4. the wake summary opens a turn after a session stopped while you were away;
5. nothing renders as `[object Object]` or an empty card;
6. the nav moves between all six roots — Shepherd, Flock, Projects, Queues, Kanban, Settings — and
   **exactly one is visible at a time**. Queues and Kanban are placeholders and should say so rather
   than look broken. The Needs-You rail is **gone from the shell by decision** (**D66**), so its
   absence is correct and its return anywhere but the Flock page is not;
7. the Flock's third pane still gives you a real terminal — **D67** relocated the session view
   rather than deleting it, and the terminal is the one part of this product that cannot be
   re-derived from a projection;
8. **with JavaScript disabled, what do you get?** This is the weakest claim in the tree and it got
   weaker on 2026-09-22. There is no `<noscript>` anywhere in `src/` and there never has been; the
   shell is now one document that `app.js` reveals a root of, so with JS off the likely result is an
   empty frame. Two seconds to check, and it was already recorded as *unguarded* before the
   redesign. Treat a bad answer here as expected, not as a surprise.

Also worth your eye once: `docs/probes/2026-09-17-m4-sdk/FINDINGS.md` (what the engine actually does),
`docs/evidence/m4-master-system-init.json` and `docs/evidence/m4-live-master-run.json` (what a real master was
started with, and the audit records it produced).

**`MacHost` ships honest-but-unverified** — `verified()` is `False` and says so. The port has now been
run on a Mac and the suite passes, but the five named captures at M1's G1 were never taken, so the
flag stays `False` and this paragraph stays true.

## What the QA pass found, and what is still open

### QA round 5 (2026-09-22/23) — the Projects backend and the UI

The most recent pass, and the first to run the full seven-link cc10x QA route. Harness:
`tests/qa5/` — 22 files, 6,974 lines, 35 scenarios over six waves, mutation floor 11/11. Report:
`.cc10x/qa/wf-20260921T212808Z-9172ed6b/report.md`.

**One real product defect, and it is a class rather than an incident.** *The pane belonged to the
last read that resolved, not the last one asked for.* An async read wrote shared view state and
painted without checking its write was still wanted, so tapping B while A was still loading left
B's data under A's heading. Found on Projects, then found again on sessions. Fixed in `7487f1a`
and `b24d46a` by making the intent (`view.openId`, `view.openSessionId`) a synchronous write the
async continuation re-checks. Reproduced deterministically — a page-level `fetch` shim that parks
one read and releases it after a newer one has painted, not a timing guess.

**One candidate open, low:** `#stream-status` still reads `live` 30 s after the daemon stops.
No oracle for what the correct timeout is, so it is recorded rather than patched.

**The round's real yield was eleven defects inside the harness built to find defects** — which is
this repo's dominant failure mode recurring one level up, and the reason the round was worth
running. The worst of them: **the run report could not express a failure at all.** Measured: 140
emitted artifacts, `FAIL` total 0, and 47 all-green reports carrying `scenarios: 0`, each of which
had gone on to overwrite the published `qa5-latest.json`. Publication is now gated on record-set
completeness. Two others are worth naming because each had a precedent in this tree: the harness
re-introduced a `"kill-server" in argv` membership test — the exact check tmux defeats by prefix
resolution, which the product had already fixed and documented at `tmux_cmd.py:326` after an
incident — and it hard-coded a `760` width literal inside the instrument written to report
hard-coded widths.

**A preflight near-miss worth remembering:** `rm -rf $SCRATCH` would have destroyed a registered
git worktree of the repo under test, while teardown's `git status --porcelain` reported clean.

### The earlier M1–M4 pass

The first pass to test the four milestones **composed** rather than each one's own seams found five
defects. Two are fixed:

- **The orchestrator could never be told what stopped while you were away.** The wake query filtered on
  an origin **nothing in the tree wrote** — every spawn, the master's included, wrote a different one.
  Every wake test passed because each planted its own row. Fixed by binding the caller into the tool
  call, so a spawn's origin depends on **who asked**; proved by a master-initiated spawn reaching the
  wake set, never a fixture row.
- **The Needs-You rail never showed an approval** — the spec's own mock has three row kinds and the
  third was invisible on every page. Fixed as a composition, with each row naming its actual ask.

Three are recorded with reasons rather than patched: `shepherd status` cannot see a running daemon's
fleet (needs a transport decision *and* a second byte-freeze re-base, owed together); a shutdown
outcome that is deterministic rather than racy (a correction to a ledger sentence); and the two
install-path edges above.

**Still open, all named with owners** in `docs/plans/m1-m4-qa/` and `docs/plans/m4-blockers/`:
`fleet_summary` is 85 lines at *one* session against a documented ~40 and grows linearly — **measured at
92 lines for 5 sessions, 127 for 25 and 428 for 200** (`router-decisions.md`) — a design decision with
two viable options; per-caller *scope* is now expressible but `caller_id` is still an
unauthenticated self-stamp; and a tier-2 tool binding that was **cut on a security finding**, with its
reversal condition written down.

## Where the reasoning lives

`docs/plans/m4-blockers/router-decisions.md` is the decision ledger — every design call, who made it,
and what was measured. `docs/plans/m1-m4-qa/` holds the QA plan, the harness notes, the defects and the
fixes. Each milestone has its own `*-BLOCKERS.md`. The ledgers record survivors, bad mutations and
"what this did not prove" as standing sections, so a later reader inherits the doubt as well as the
result.
