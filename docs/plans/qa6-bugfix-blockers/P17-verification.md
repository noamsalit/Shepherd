# P17 — qa6 verification of the bugfix branch

Branch `qa/round6-full` (local, never pushed). Code at `1246e86`; harness rounds 5–7
(`5fa7418`, `67c3041`, `d7bbc70`).

## Runs

| Run | Scope | Result |
|---|---|---|
| `qa6-20260924T124009Z` | full, 161 | 125 PASS / 28 FAIL / 8 BLOCKED (run 2: 97 / 62 / 2) |
| `qa6-20260927T061932Z` | wave 6 (readiness-gate fix) | 30 PASS / 4 FAIL (U7 U8 U10 U14) / 0 BLOCKED |
| `qa6-20260927T062958Z` | waves 1 + 8 (W2 fix) | W1–W5 PASS; L1 L3 L8–L11 PASS; L4 L5 FAIL; L2 L6 L7 BLOCKED |

- FAIL→PASS: 32 (C9 C10 D2 D9 D13 E1 E5 L11 M7 M16 M18 M19 O6 P2 R2–R5 T4 U2 U11 U13 U17 U18 U24 U25 U30 U38–U41 U45).
- PASS→FAIL: none.
- U4 U6 U34 U35 U37: BLOCKED in the full run by the harness gate (`inner_text` of a
  `visibility:hidden` drawer); PASS after round 6.
- L5: only `stream.session_spawned_untrusted` still fails (pre-existing); the BC-01 clause
  and the ±5 min timing clauses pass on an awake host.
- L2: BLOCKED(model) — `master.rate_limit` during the turn; PASS in the full run.
- L7: BLOCKED(timing) as planned (m2 answered before m3 could be sent mid-turn).

## Remaining FAILs (28) — none is a regression

| Cause | Scenarios |
|---|---|
| Owner decision | BC-05 C1–C5 · BC-14 M12 · BC-15 M14 · BC-20 H4 · BC-21 C7 · BC-28 O4 · BC-06 U26 · BC-32 A4 (parked `fix/qa6-P10-bc32-owner`) |
| Spec vs design (SD-01..10) | D12 U7 U8 U27 U28 U10 T3 U14 O9 O10 O12 H5 |
| Wrong test expectation | M9 O8 L4 |
| Pre-existing | L5 (untrusted spawn) |

## Host safety

- `~/.claude/settings.json` sha `f99112b6…` unchanged across every run (INC-3: differs from
  the owner-named `28067dc4…` since 09-24 12:34, not caused by a run; unattributed).
- `~/.local/bin/claude` → `2.1.283` before and after (auto-update 09-27 09:13, before the reruns).
- tmux sockets: only `shepherd-m3-*`; no `/private/tmp/shq6-*` left.
