# Shepherd — handoff, 2026-09-18

M1 through M4 are built, verified and QA'd. This file is what you need to take it to a Mac, plus an
honest list of what is **proved**, what is **recorded as unverified**, and what is **still open**.

## State

| | |
|---|---|
| default suite | **1840 passed, 1 skipped, 75 deselected** |
| live lane (`pytest -m live`) | **75 passed** — starts real `claude` processes and real tmux panes |
| boundary rules | **105 passed** |
| `mypy --strict src` | clean over **127** files, `disallow_any_explicit` on |
| composition root | `daemons/controld.py` still **140** lines, guard constants unedited |
| your settings file | `~/.claude/settings.json` sha256 `375e5322…d6ac` — **never written, checked on both sides of every live test** |
| your tmux | socket `shepherd` never named in a write; `m3` and `master` untouched |

Nothing is committed. One baseline commit exists; everything since is working tree, as instructed.

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

**Nothing is installed on this host** — the three console commands exist only as declarations, which
is why the QA pass drove a real `pip install -e .` into a throwaway venv (scenario S9). On the Mac:

```
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/shepherd doctor           # start here: it reports engine, schema, database, discovery
.venv/bin/shepherd status
.venv/bin/shepherd-controld --port 8787
```

Then open `http://127.0.0.1:8787/` — chat is the default landing, the fleet is page 2.

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

**`MacHost` ships honest-but-unverified** — `verified()` is `False` and says so. You will be the first
to run it; five named things need capturing on a real Mac, listed at M1's G1.

> **Updated 2026-09-20 — that first run happened.** Three of G1's five closed by measurement on a real
> Mac (macOS 26.6.2, arm64): the 103-byte `sun_path` budget, the netcat flag set, and the
> `TMPDIR`-derived runtime dir. `docs/probes/2026-09-20-macos-g1-capture.md` is the capture, and the
> annotations in `src/shepherd/host/mac.py` now say `VERIFIED (docs/probes/…)` for exactly those three.
>
> The headline is that **there is no `timeout` on a stock Mac**, so `hook_dispatch()` could never be
> available there and the signal engine would have received nothing. It is now
> `perl -MTime::HiRes=alarm -e 'alarm 0.25; exec @ARGV or exit 0' nc -U <sock> || true` — stock
> `/usr/bin/perl` and `/usr/bin/nc`, measured delivering both captured frame sizes byte-for-byte and
> bounding a wedged `sessiond` at 264–324 ms. Do **not** "simplify" it to `nc -U -w 0`: that truncates
> a 40 KB frame to ~16 KB, silently, 3 runs out of 3.
>
> `verified()` is still `False`, and still honestly: `launchctl print gui/<uid>` and
> `ps -o lstart=` / `LOCAL_PEERCRED` remain uncaptured. Two of five, not none of five.

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
`fleet_summary` is 85 lines at *one* session against a documented ~40 and grows linearly — a design
decision with two viable options; per-caller *scope* is now expressible but `caller_id` is still an
unauthenticated self-stamp; and a tier-2 tool binding that was **cut on a security finding**, with its
reversal condition written down.

## Where the reasoning lives

`docs/plans/m4-blockers/router-decisions.md` is the decision ledger — every design call, who made it,
and what was measured. `docs/plans/m1-m4-qa/` holds the QA plan, the harness notes, the defects and the
fixes. Each milestone has its own `*-BLOCKERS.md`. The ledgers record survivors, bad mutations and
"what this did not prove" as standing sections, so a later reader inherits the doubt as well as the
result.
