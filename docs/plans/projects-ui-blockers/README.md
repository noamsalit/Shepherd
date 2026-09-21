# Projects + UI blocker entries — one file per task

**Why this directory exists, and why it is not one file.** M4's ledger started as a single
file every builder appended to. Four builders were live at once; one rewrote it whole instead
of appending, and **Task 2's and Task 8's entries were destroyed**. They were reconstructed
from the builders' hand-back reports, but a reconstruction is not the original. The process
error was the router's: *"append to this file"* is an instruction, not a concurrency protocol.
`docs/plans/m4-blockers/README.md` carries the full account.

## The rules

1. **One file per task.** A builder writes `docs/plans/projects-ui-blockers/<task-id>.md` —
   `t0-1.md`, `t1-10.md`, `t5-3.md`. The id is the plan's task id, lowercased, with the dot
   written as a hyphen.
2. **Nobody opens another task's file.** Not to read-and-rewrite, not to tidy, not to
   cross-reference by editing. Cross-reference by **id**, which resolves wherever the entry
   lives.
3. **An entry is** `T<id> · symptom · what was tried · what it blocks · owner`. All five
   fields, every time. "What was tried" is the one a reader cannot reconstruct later, and it
   is the one most often left out.
4. **Ids are never reused.** This is also why there is no Phase 2 in
   `docs/plans/2026-09-21-projects-and-ui-plan.md`: it was folded into Phase 1 at revision 2
   and its number was **retired rather than re-flowed**, so every reference already written
   down still resolves. Re-flowing ids silently invalidates every citation made before the
   re-flow — including the ones in a review that is already finished.
5. **An entry is never deleted — only retired in place.** A retired entry says it is retired,
   says why, and names the decision that retired it. A deleted entry reads, to the next
   reader, as an entry that never existed.
6. **Never a shared ledger.** If a readable roll-up is wanted, only the router assembles one,
   from these files, and only when no builder is live.

## What belongs here

Anything that blocked, surprised, or cost time: a required check that could not pass inside a
task's Allowed Scope, a measured fact that contradicts the plan, a flake, a tool that had to
be fixed before it could be used. A finding recorded is a finding the next task does not have
to re-derive. A phase that reports *partial* with a ledger entry is worth more than one that
reports *done* and is not.
