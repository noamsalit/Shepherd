# M4 milestone verification

Verify that **M4 (the orchestrator) is done**, against its own acceptance criteria. You are not
reviewing code quality and you are not fixing anything. You decide, clause by clause, **PASS / FAIL /
UNVERIFIED**, and the only currency you accept is a command you ran and its output.

## The criteria
`docs/plans/2026-09-17-m4-orchestrator-plan.md`, section **"## Milestone acceptance — M4 is done when"**.
**There are TWENTY-ONE clauses.** Read the whole section; do not read it through a `sed` window. M2's
verifier was briefed on 13 of 16 because a window cut three. **Count them yourself and say the number
you counted before scoring anything.** Clause 21 was added by the router mid-milestone and says so.

Score **every** clause. A clause you cannot check is **UNVERIFIED with the reason**, never a silent PASS.

## The tree, measured by the router minutes ago on a quiet tree
- default lane: **1772 passed, 1 skipped, 57 deselected**, exit 0
- live lane (`pytest tests/e2e -m live`): **30 passed, 3 deselected**
- `tests/boundaries`: **86 passed** · `mypy --strict src`: clean over **126** files
- `wc -l src/shepherd/daemons/controld.py`: **140** · `PENDING_SITES`: **empty**
- `~/.claude/settings.json`: `375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac`
- `tmux -L shepherd ls`: `m3`, `master` — the user's own, untouched

**Do not take these from me. Re-measure every one you use**, and say so if any disagrees.

## Read before scoring — findings already known, not yours to discover
`docs/plans/m4-blockers/router-decisions.md` is the decision ledger; `docs/plans/m4-blockers/t*.md` are
the per-task records. **`t7.md` does not exist** — T7's findings are §T7-1…§T7-8 of
`docs/plans/2026-09-17-m4-BLOCKERS.md`.

Nine items you must judge rather than rediscover:

1. **G-M4-8 — measured and confirmed.** `fleet_tree` is **139 323 B (~35k tokens)** at 200 sessions;
   §11 promises *"~40 lines regardless of fleet size"*. Both projections are `{HUMAN, MASTER}`, so **the
   master can call a 35k-token tool**, and M4 is the milestone that gives it the ability. Unfixed
   deliberately (M1 code no M4 task owns; the fix is a design decision). Three options are written up.
   **A verifier scoring §11's sentence against this tree would be scoring something it does not honour.**
2. **§T25-8 — a real production race.** A worker freed by shutdown's withdrawal can meet a closed store
   and raise instead of returning D54's refusal (the HTTP server runs on threads shutdown does not own).
   Clause 20's promise — nobody left **blocked** — holds and is asserted; the test records *answer or
   raise* rather than laundering one into the other. Judge whether clause 20 is honestly satisfied.
3. **§T26-6 — a capability with three producers.** The withdrawal key is produced at
   `TurnDriver.interrupt_master`, `AgentSDKMaster.interrupt` **and** `AgentSDKMaster.close`; each is
   independently sufficient, so **no single-site mutation of it can ever be red**. Not a defect —
   redundancy — but it means anyone repairing one site and seeing green is wrong about why.
4. **RD-T6-PYC — stale bytecode can record a false survivor.** 7 of 9 mutation drivers did not clear
   `__pycache__`. **Recorded REDs are unaffected**; the exposure is to survivors, and every unintended
   survivor was chased down. Judge whether that reasoning holds.
5. **The QA-prep list — four items, three of them one defect**: a boundary helper blind to call-shaped
   imports used bare by **fifteen** shipped rules; a rule that existed in **three** implementations; an
   identifier scan that sees dotted names only, so bare `open(path)` is invisible. All M1–M3 code M4
   merely surfaced.
6. **Two duplicated constants** held by drift guards (redaction markers, `actor_kind_of`), both forced
   by a transitive-import constraint the shipped rule cannot see. One-line fix named, in `types.py`.
7. **`autonomy_level: 0`** in every audit record is `UNREPORTED_AUTONOMY_LEVEL` — the gate has no route
   to the level it read, and writing `2` would be K23's overclaim. Judge the honesty of that choice.
8. **Track C was cut** (a deviation from §16: M4 ships **one** MCP exporter, not two) on a security
   finding: the registry discards the caller after the audience check, so no handler can scope a
   request, and six `SESSION`-audience tools take arbitrary ids. Prerequisite for ever shipping it is
   written down.
9. **T8-3 row 7 is OPEN**, and the plan's "one line" estimate was measured wrong — three files and a
   design decision.

## How to verify, in this repo
**The dominant defect class is "a check that reports success without checking."** A green test proves a
test passed. For each clause ask **what mutation it would survive**.
- Where a clause rests on a check, **plant the violation and confirm red** — in **`scratchpad/m4-verify/shadow/`**
  (`src/` *and* `tests/` copied, pytest run with `cwd=` the shadow), **never the live tree**, and
  **clear `__pycache__` before every run** (see item 4 — that is how a false survivor happens).
- **Never plant a signal, a `kill`, a teardown verb or any reboot-capable call into executable code in
  any tree.** A mutation planted in a shadow copy rebooted this host on 2026-09-17; `CLAUDE.md`'s
  mutation section and spec §18 carry the incident.
- A check with no mutation proof and no obvious bite is **UNVERIFIED**, not PASS.

## Rules
- **Read-only on the product.** You write only your report and your own shadow.
- **Never run `tmux kill-server` without `-L`**; the user's live sessions are on socket `shepherd` —
  never name it in a write. **Session names are read, never hard-coded.** Throwaways are `^shepherd-m4-`.
- **Never write under `~/.claude/`**; check its hash before and after.
- The live lane may be run — print and check every tmux argv first, and confirm no `claude` survives.
- Do not `git commit`. `docs/probes/` is read-only frozen evidence.

## Report
All 21 clauses with PASS / FAIL / UNVERIFIED and, per clause, the command and output that decided it.
Then: the mutations you planted and their verdicts; every clause whose **wording** you judge wrong, with
the correction; your judgement on each of the nine items above; and the final numbers.

M2 returned FAIL on 2 of 16; M3 on 4 of 17, three of which were the plan claiming proof it did not have.
**That is the expected yield. An all-PASS on a milestone this size is more likely a verification that
did not bite.**
