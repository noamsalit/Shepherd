# Shepherd — handoff

**Last updated 2026-09-21.** M1 through M4 are built, verified and QA'd. This file is what you need
to take the project anywhere, plus an honest list of what is **proved**, what is **recorded as
unverified**, and what is **still open**.

## State

| | |
|---|---|
| default suite | **1866 passed, 2 skipped, 75 deselected** on Linux |
| live lane (`pytest -m live`) | **75 passed** — starts real `claude` processes and real tmux panes |
| boundary rules | **105 passed** |
| `mypy --strict src` | clean over **127** files, `disallow_any_explicit` on |
| composition root | `daemons/controld.py` still **140** lines, guard constants unedited |
| decisions | **65** (D1–D65, plus D38.1) in `docs/specs/orchestrator-platform.md` §3 |
| your settings file | `~/.claude/settings.json` sha256 `375e5322…d6ac` — **never written, checked on both sides of every live test**. Shepherd's hooks are **not installed**. |
| your tmux | socket `shepherd` never named in a write. The **socket** is the invariant; session *names* are not, and any check written against them goes red the next time you open a terminal. |

## Git state, as of 2026-09-21

Read this before assuming anything about the repository — an earlier version of this file said
*"nothing is committed"*, which stopped being true on 2026-09-18.

- **`main`** `bd10b01` — M1–M4, and the history that was pushed public before the identifier scrub.
- **`docs/publish-prep`** `85000d5` — the scrub, plus the 2026-09-20/21 documentation.
- **`clean-root`** `8685558` — a **parentless** commit carrying the scrubbed tree, made with
  `git commit-tree` so nothing destructive ran.
- **`integration`** — `clean-root` plus the macOS port, six commits, **author and committer
  `Noam Salit <nsalit@gmail.com>` throughout**, and **zero employer-identifier hits in every
  commit's tree**, not only at the tip. This is the branch intended to become the published `main`.
- **`macos-original`** `dade5685` — the macOS branch as it arrived, kept for comparison.

A remote exists: `origin git@github.com:noamsalit/Shepherd.git`. The published repository predates
the scrub, which is why the plan of record is to delete and recreate it from `integration` rather
than to rewrite history in place.

**Backups** live at `/root/shepherd-backup-20260920/` — bundles and worktree tarballs, each verified
by restoring it and comparing tree hashes rather than by checking the file exists.

## What changed on 2026-09-20 / 21

Documentation and design only, with two exceptions, both named. **Nothing under `src/` changed
except one comment line in `web/static/rail.js`** (part of the identifier scrub, commit `85000d5`),
and one test was repaired — see below. That repair exists on **`integration`**, not on
`docs/publish-prep`.

- Every employer-associated identifier was removed from the tree. The override that allowed editing
  frozen probe evidence, and its three standing conditions, are recorded in `CLAUDE.md`.
- **D56–D64** added. D56 fixes which seam a future engine class may arrive through. **D57–D64 describe
  work that is not built**: project lifecycle, `Unassigned`, repo↔project many-to-many, delete
  semantics, discovery switches, per-project work sources, provider-declared filters.
- New documents: `docs/specs/logical-architecture.md`, `docs/specs/harness-contract.md`,
  `docs/specs/credentials-and-auth.md`, `docs/design/ui-decisions.md`,
  `docs/backlog/2026-09-21-projects-work-sources-and-ui.md`.
- **A dark-mode UI redesign**, as a clickable prototype and not as code:
  https://claude.ai/artifact/1HFNab8sksQdz7WAP4SfFc — with the pre-redesign UI rebuilt beside it at
  https://claude.ai/artifact/JMSzca6pWM38GHuFVmNQeE. Decisions in `docs/design/ui-decisions.md`.
  **No file under `src/shepherd/web/` was changed.**
- **One test repaired** (`tests/engines/test_hook_dispatch_delivery.py`): a negative control passed on
  macOS and failed on Linux because its 40 KB frame fits inside Linux's 212,992-byte socket send
  buffer and so never wedged. It now uses a 1 MB frame, sized clear of both platforms.

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

**The macOS port landed on 2026-09-20** and the suite passes there; its commits are on `integration`.
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

Then open `http://127.0.0.1:8787/` — chat is the default landing, the fleet is page 2.
(The redesign renames these *Shepherd* and *Flock*; that is design only and not in the code.)

**Two rough edges on that path, both measured and both minor:** `shepherd --help` answers
`unknown command '--help'` (exit 64), and `shepherd-sessiond` with no arguments is an argparse error
because `--expected-schema-version` is required — deliberately, so a relay cannot start against a
schema it was not built for. Both are behind a byte-freeze on `cli/` that has spent its one permitted
re-base, so they are recorded rather than patched.

## What a human must check, because this host cannot

**No browser, no node, no npm here.** Every web claim in the tree is bytes on disk or bytes on a
socket; **nothing claims the page renders.** On the Mac:

1. the conversation streams line by line when you send the master a message;
2. an approval card appears **and both buttons resolve it** — and it leaves both the sidebar and its
   inline position;
3. the autonomy toggle shows the current level and changes it;
4. the wake summary opens a turn after a session stopped while you were away;
5. nothing renders as `[object Object]` or an empty card;
6. the nav moves between the chat and fleet pages and the Needs-You rail survives both;
7. **with JavaScript disabled, the browser shows the fleet, not an empty chat frame** — two seconds,
   and it is the degrade a mutation proved was unguarded.

Also worth your eye once: `docs/probes/2026-09-17-m4-sdk/FINDINGS.md` (what the engine actually does),
`docs/evidence/m4-master-system-init.json` and `docs/evidence/m4-live-master-run.json` (what a real master was
started with, and the audit records it produced).

**`MacHost` ships honest-but-unverified** — `verified()` is `False` and says so. The port has now been
run on a Mac and the suite passes, but the five named captures at M1's G1 were never taken, so the
flag stays `False` and this paragraph stays true.

## What the QA pass found, and what is still open

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
