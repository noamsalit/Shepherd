# qa6 owner rulings — 2026-09-27

The owner accepted every suggestion below on 2026-09-27 ("All sounds great - go ahead and use
cc10x to fix all of them"). BC-05 was discussed first ("I think control socket is better" →
"sounds good"). INC-3: "I'm not sure what I changed but might very well be."

Sources for each item: `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md` §8 (BC-nn / SD-nn
headings), `docs/plans/2026-09-24-qa6-bugfix-plan.md` (owner-question table, lines ~140-160),
`docs/plans/qa6-bugfix-blockers/README.md` §"Owner decisions", and
`docs/plans/qa6-bugfix-blockers/P17-verification.md` (what still fails).

Branch: `qa/round6-full`, local only, never pushed. Spec §3 decision rows: any ruling that reverses
or refines a numbered D-row gets a NEW numbered row with its reasoning (spec §0; D66 is the example).

## Rulings

| # | Item | Scenarios | Ruling |
|---|---|---|---|
| 1 | BC-05 | C1–C5 | CLI reaches a running controld through a NEW dedicated owner-only (0600) Unix RPC socket, separate from the one-way control-ingest socket. One JSON request → `toolsurface.registry.invoke()` with the HUMAN audience (same gate and audit as the web UI) → one JSON reply. Reuse the socket claim/unlink helpers. Covers status, doctor (discovery + hooks lines), install-hooks, uninstall-hooks, replay, recompute. A declared edit of byte-frozen `cli/` is authorised, including `replay --since 2026-13-45` → usage error exit 64. |
| 2 | BC-06a | U26 | A tool call and its result render as ONE expandable step (call = title, result inside). |
| 3 | BC-06b | U26 | `turn_ended` and `rate_limit` go to the status slot, not the thread; a rate limit appears in the thread only when it stops the turn. |
| 4 | BC-06c | U26 | Do not render the SDK's final `result` text when it equals the last assistant text. |
| 5 | BC-14 | M12 | Level 3: when a master-spawned session stops `unfinished`/`error`, open an unprompted master turn that sends the wake summary; if a turn is running, queue it; it counts toward D31's 2-per-lineage cap. |
| 6 | BC-15 | M14 | Retry is declared explicitly: `retry_of` argument on `spawn_session`, taught in the master prompt; `Store.link_retry` enforces the cap. |
| 7 | BC-20 | H4 | `.shepherd-backup` keeps the FIRST pre-install image, never overwritten. `uninstall-hooks` keeps removing only our entries (no byte-for-byte restore). The mode-000 PermissionError part is already fixed (P9) — verify. |
| 8 | BC-21 | C7 | Re-word ADR-7 §4 to "frozen before the server serves"; controld binds the port before opening the DB, so a busy port writes nothing. |
| 9 | BC-28 | O4 | Keep the pre-written row on a refused `runner.start`, end it with a `refused` verdict (visible attempt, C-M3-7 intent). Update O4's oracle accordingly (no ghost card = the row is ended, not live). |
| 10 | BC-37 residual | — | A kill of an owned session after a finished turn records verdict `killed`; "a session end arrived during the kill" = `ended_at` changed across the kill. `tests/orchestration/test_lifecycle.py:372-416` pin updated with a declared reason. |
| 11 | BC-32 | A4 | Option (b): `test_web_server_is_byte_unchanged` accepts a declared `post_milestone.edits` entry; merge `fix/qa6-P10-bc32-owner` @ `9aa9f11` onto the branch under that declaration. The digest pin stays. |
| 12 | H3 | — | New AnomalyKind `master_failed`, recorded when a master turn fails, visible in the audit log. |
| 13 | H1-lock | — | controld (and sessiond, same shape) holds an `flock` on a lock file for its whole lifetime; closes the claim→bind race (residual E16). |
| 14 | SD-01 | D12 | Keep the code's stop-map; update the spec text (DP8) to match. |
| 15 | SD-02 | U7 | Keep the AA-adjusted legend tint; fix the U7 oracle / design note. |
| 16 | SD-03 | U8 | Keep week/month units; fix the design doc's U8 example. |
| 17 | SD-04 | U27, U28 | Keep the decided card inline with its outcome label; update HANDOFF checklist item 2 and the oracles. |
| 18 | SD-05 | U10, T3 | Build terminal input: typing in the terminal view sends keystrokes to the pty (spec C-19). |
| 19 | SD-06 | U14 | Make decision-card choices clickable, routed through the existing, working HTTP answer route (`answer_permission`). |
| 20 | SD-07 | O9 | A message to an attached (pane-less) session is refused at send time with NO durable row (spec O51). |
| 21 | SD-08 | O10 | `ask()` returns Shepherd's ULID as `from_fork_of`; the engine session id travels as a separate field. |
| 22 | SD-09 | O12 | Build the channel for sessions to reach Shepherd's tool surface (message + spawn each other), reusing the BC-05 RPC socket; until it ships, the README marks capability 3 "not yet". |
| 23 | SD-10 | H5 | Keep partial install + warning; fix the H5 oracle / spec text. |
| 24 | M9 | M9 | Test fix: expect `approved_by: policy`. |
| 25 | O8 | O8 | Test fix: assert the delivered count, not the pending list. |
| 26 | L4 | L4 | Test fix: accept a stopped (non-ephemeral) row for a hooked `-p` session. |
| 27 | L5 | L5 | Code fix: a newly spawned session's `session.spawned` frame carries `trusted: false` until trusted. |
| 28 | INC-3 | U2 | Accept `f99112b6db8b5adb5014792c84e75cac806ec12ecb73a2dee3a1ef95a7f1c52b` as the owner-named settings sha in `tests/qa6/paths.py` `OWNER_SETTINGS_SHA`. |

## Standing constraints

- Never touch the real `~/.claude/settings.json`, port 8787, the default tmux server or socket
  `shepherd`, or `~/.local`. Never push. No bare `git stash`. Quoted heredocs only.
- Python 3.12, `mypy --strict`, no `Any`, no `print`, small single-purpose functions.
- Boundary rules: `consumer_manifest.json` `baseline` is never rewritten; declare `post_milestone.edits`;
  whole-set assignment pins (`test_session_wiring.py`, `test_settings_page.py`, `test_chat_page.py`).
- Worktree builders run `PYTHONPATH=$PWD/src /Users/noamsalit/Git/Shepherd/.venv/bin/...`.
- Baseline reds (P0) stay exactly as recorded in `docs/plans/qa6-bugfix-blockers/P0-baseline.md`.
- Acceptance: each ruling's scenario(s) flip to PASS in qa6 (or its oracle is corrected with a
  recorded reason), with 0 PASS→FAIL regressions against `qa6-20260924T124009Z` + the 09-27 reruns.

## Decomposition and build order (exploration, fast path)

The rulings span independent subsystems, so the plan sequences them as separate phases:

1. **Harness and oracle corrections** (#15, 16, 17, 23, 24, 25, 26, 28) — tests/docs only, no product code.
2. **Small product fixes** (#7, 9, 10, 12, 20, 21, 27) — each one module plus tests.
3. **Master chat rendering** (#2, 3, 4) — `web/static/chat.js` plus its pins.
4. **Master orchestration** (#5, 6) — level-3 wake and declared retry; spec D31 refinement row.
5. **Daemon startup** (#8, 13) — bind before DB, lifetime flock; ADR-7 §4 re-word.
6. **BC-32 merge** (#11) — boundary test accepts a declared edit, merge `9aa9f11`.
7. **CLI RPC socket** (#1) — new socket in controld, client in `cli/`, six commands, `--since` exit 64.
8. **UI interaction** (#18, 19) — terminal input to the pty; clickable decision-card choices.
9. **Session tool channel** (#22) — README "not yet" lands with phase 1; the channel itself builds on
   phase 7's socket and is the last phase. If its design needs a spec row the plan cannot settle, the
   planner records it as an Open Decision for that phase only, and phases 1–8 proceed.
10. **Spec text** (#14 SD-01 DP8) — lands with phase 1.

Rejected alternatives (ADR notes):
- BC-05 over loopback HTTP — rejected: any local process can reach the port, the needed tools are not
  routed, and `web/server.py` is digest-pinned.
- BC-05 multiplexed on the control-ingest socket — rejected: that wire is one-way sessiond→controld
  with a schema-versioned hello; request/reply there changes every running sessiond.
- BC-20 byte-for-byte restore on uninstall — rejected: loses the user's edits made since install.
- BC-15 inferred retry (same brief + cwd) — rejected: false positives and negatives on the cap.
