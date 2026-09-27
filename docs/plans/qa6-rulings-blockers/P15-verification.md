# P15 — qa6 verification against the comparison set

Workflow `wf-20260927T110316Z-ee74fe07`. Main checkout `/Users/noamsalit/Git/Shepherd`, branch
`fix/qa6-rulings`. Executed 2026-09-27 by the router (the P15 executor agent was stopped by a
session restart; its comparison script `scratchpad/p15/compare.py` was reused unchanged).

## Verdict: PASS (exit criteria met)

| | Baseline (combined, plan step 3) | P15 |
|---|---|---|
| PASS | 129 | **153** |
| FAIL | 28 | **1** (O12, SD-09 deferred, expected) |
| BLOCKED | 4 | 7 |

- FAIL → PASS: **24**
- PASS → FAIL: **0** (scenario and clause level)
- PASS → BLOCKED: **0**
- Vanished PASS clauses: only U7's 26 and U15's 2 clauses whose names end in a per-run random
  session id (`ui.card_colour.running.<ID>`). Each run mints new ids; in the P15 run all 28 are
  present under new ids and all PASS. Declared renames: `C2 logs.database_schema_4` (P4),
  `L8 api.from_fork_of_engine_id` (P7).

Records: full run `qa6-20260927T200207Z` (HEAD `c835a0f`), overlaid by the waves 1–3 re-run
`qa6-20260927T201849Z` (HEAD with the C2/C4 oracle fix below). Both under
`.cc10x/qa/wf-20260923T182839Z-9adb11fc/runs/`.

## Owner-named blockers

| Blocker | Scenarios | P15 |
|---|---|---|
| BC-05 CLI reaches the daemon | C1, C2, C3, C4, C5; W4, D10, M19 (4-thread stop line) | all PASS |
| BC-06 one step per tool call / event line | U27, U28, L1 PASS; U26 BLOCKED (below) | PASS via L1/U27/U28 |
| SD-05 terminal keystrokes | T3, U10 | PASS |
| SD-06 clickable choices | U14 PASS; L6 BLOCKED (topology) | PASS via U14 |
| SD-09 session tool channel | O12 | FAIL — deferred by the owner (backlog doc) |

## Fixes the run itself found (all committed on `fix/qa6-rulings`)

1. `b725064` harness: preflight T1 hard-coded branch `qa/round6-full`; now also `fix/qa6-rulings`
   (ancestry from dc913fc still checked). Also RD-2 prints the lineage depth (P13b review F1).
2. `56bb015` harness: P3's L1 edit reused `before`, overwriting the files snapshot (T4 mypy).
3. `4fbd831` **product**: D79's master-failed audit row wrote autonomy level 0 (M16 PASS→FAIL);
   it now records the level in force.
4. `c835a0f` harness: sessiond was started with `--expected-schema-version 4`; migration 005 made
   it 5, so every probe frame was a schema mismatch (D12, L4, U7–U14, U41–U45 BLOCKED; D12's
   leftover sessiond then blocked H6, C6, C4). Now `EXPECTED_SCHEMA_VERSION`.
5. C2/C4 oracle text (this commit): the checks looked for wording the product never printed
   (`registry sessions 2`, `managed`, an unindented `read N records`); the product prints
   `registry 2 sessions`, `N of our entries`, `  read N records`. They had failed in every
   baseline too, masked by C-1 (no daemon). Declared changed clauses:
   `C2 logs.discovery_reports_the_daemon`, `C2 logs.hooks_reports_managed_entries`,
   `C4 proc.replay_since_read_n_records`, `C4 proc.recompute_read_n_records`.

## Remaining non-PASS (none is a regression)

- **O12** FAIL — SD-09, deferred (`docs/backlog/2026-09-27-sd09-session-tool-channel.md`).
- **U26** BLOCKED — the scripted `ToolCallingMaster` emits one `text` per turn, so "two prose
  lines" cannot be scripted without a harness change. Behaviour proven live by L1.
- **R1** BLOCKED — unobservable as written (the Flock draws no running count). Pre-existing.
- **L2** BLOCKED(model) — no approval card after one retry; model nondeterminism (it PASSed in the
  same-day diagnostic run).
- **L4, L5, L6** BLOCKED(topology) — needs_real_home reads the sandbox cfg (Difference 11).
  Pre-existing harness topology.
- **L7** BLOCKED — timing: m3 was not sent mid-turn.

## Host safety (before / after, compared semantically)

- `~/.claude/settings.json` sha `f99112b6…c52b` both times.
- `~/.local/bin/claude` → `versions/2.1.283` both times.
- tmux socket dir: same 9 names, listed only, never connected to.
- 8787: the owner's pid 48395 both times.
- No `/private/tmp/shq6-*` left.
- INC-1 guard notes during re-runs: `~/.local` changes were the owner's own tools (cursor-agent
  self-update, Claude Code removing old versions 2.1.267/2.1.268) — not the harness.
