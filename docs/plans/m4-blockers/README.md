# M4 blocker entries — one file per task

**Why this directory exists.** M4's ledger started as a single file every builder appended to. Four
builders were live at once; one rewrote it whole instead of appending, and **Task 2's and Task 8's
entries were destroyed**. Task 9 found the hole while trying to read `§T8-3`, which the plan
instructs Task 10 to consult. The entries were reconstructed by the router from the builders' own
hand-back reports — the primary source, which survived — but a reconstruction is not the original.

**The process error was the router's.** "Append to this file" is an instruction, not a concurrency
protocol. It was the same shared-file hazard `tests/conftest.py` hit in M3, and the lesson did not
get carried across.

**The rule from here:** a builder writes **`docs/plans/m4-blockers/<task>.md`** — its own file, which
nobody else opens. `docs/plans/2026-09-17-m4-BLOCKERS.md` stays the readable ledger and is assembled
from these; only the router edits it, and only when no builder is live.

A finding is still addressable by its id (`T8-3`) wherever it lives. Ids are never reused, and an
entry is never deleted — a retired one says so in place, the way `ADR-M4-4` and `DP6` were retired
rather than removed.
