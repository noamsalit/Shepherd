# `cc10x_artifacts` lane — §3 What the artifacts say prior rounds could NOT see

## THE PROCESS BLIND SPOT (json:817-819) — the headline
Rounds 1-4 **never routed to QA**. `workflow_type` stayed PLAN, the `qa` block was null, and only
`qa-executor` — the LAST of seven links — was dispatched, four times. So **no feature map, no test
plan, no env plan, no preflight and no harness review existed for any of rounds 1-4.** All 22
recorded defects came from a single unreviewed executor.
Corroborated: `qa.artifacts.{feature_map,test_plan,env_plan,report,setup_record}` all null;
`qa.env_key` null; `qa.preflight` unpopulated; `results.qa_researchers: []`; `results.qa_executor: null`.

## Round 3's own "did NOT prove" list (report-qa3.md:386-408)
- Anything **above 1280px or below 390px**.
- **Any real tmux pane** — every kill injected in-process; the shipped
  `kill_for_delete -> kill_session_now -> record_and_terminate` chain was untested and *forbidden*.
  **That prohibition is now LIFTED** (user authorised `-L shepherd-qa`, json:568-582).
- **The terminal WebSocket** — `/api/sessions/{id}/terminal`, `terminal.js`, `vendor/xterm.js`
  "never opened". Round 3 drove the pane's header/state/why/actions, not the live pty.
- **The production audit sink** — the chokepoint collected records into a list; what
  `build_audit_sink` writes to disk per call was never measured. The "two autonomy POSTs append two
  audit rows" claim is *reasoned, not measured*.
- `.dlg-reason` pixels at 390px — blocked by D2 at the time.
- **Real concurrency** — double-clicks were two synchronous `click()` calls on one thread. No
  two-tab, two-writer, or SSE-during-mutation race was ever driven.
- **Touch events** — synthesized mouse events only; no `touchstart` path.
- **`prefers-reduced-motion`, forced colors, zoom, RTL** — not touched.

## Round 3's SIX FALSE PROBES, reported as results (report-qa3.md:351-382)
Reported deliberately "because both prior runs produced false readings of exactly this shape".
1. Nav clicks at phone width "failed" — the off-canvas drawer was never opened; the pane sits at
   `x: -244..0` by design (app.css:1996). The closed drawer's 7 controls are now excluded BY NAME
   and counted, never silently.
2. **Off-by-one on the drawer breakpoint** — helper used `width < 760`, the media query is
   `max-width: 760px`, inclusive. **Every reading at exactly 760px was wrong.**
3. "The list still shows the deleted project" — read in the frame before `loadList()` resolved.
   Not a defect; the probe's own race.
4. "Every Flock card renders bucket-unclassified" — the seed called `apply_stop_verdict` only,
   which writes the eight stop columns but NOT `session.state`; `ordering.bucket_of` requires
   `state is STOPPED` first. Not a defect; the probe's own seed.
   **Gotcha: `test_projects_page.py::ended_session` has the same shape — harmless there, NOT
   usable for any Flock bucket assertion.**
5. "The legend keys do not filter" — they were never filters; every key binds `openLegendSheet` (U1).
6. "The tooltip blocks the info button" (first attempt) — a preceding click had reopened the sheet,
   and the sheet was the interceptor. Re-measured clean, D3 rests on the clean measurement.

## `viewport-drift` (json:412-415, 2026-09-22T17:41:18Z) — STILL OPEN
`tests/web/test_projects_page.py` and `test_settings_live.py` hard-code 1280x900 and reference
`render_check.VIEWPORTS` **zero times** — the exact drift that hid D1. Named in the D1 remediation
and still open. Was blocked on "tests/web is lane A territory until the merge"; **the merge has now
happened, so the blocker is gone.**

## `deferred_findings` — 16 entries, NONE closed. The five that matter for round 5:
- **GAP 1 `doomed`** — `DeletePlan.doomed` never reaches a consumer; the handler discards it and
  `delete_outcome` has no key. The refusal can say "2 running" but not "and 400 finished ones go
  with the project". **The page derives the count itself — a COPY of a store derivation.**
- **GAP 2 killability** — `DeletePlan.running` does not distinguish owned from attached, and the
  shipped kill answers `no_pane` for every attached session. **So the page can offer a
  `kill_sessions` button that cannot succeed, with a refusal that does not say why.**
- **GAP 4 D60 unreachable** — nothing answers WHICH projects hold this repo. (Note: partially
  addressed since — commit 42497d2 "D60 is reachable". Re-measure.)
- **GAP 5 destructive-first-call** — `delete_project` destroys on its first call when nothing is
  running, so probing for the refusal would destroy any idle project. The page confirms BEFORE it
  asks. A dry-run would close it properly.
- **Kill robustness** — `except Exception` because nothing proves the shipped kill raises only
  `RunnerRefusal`; **a kill that HANGS still blocks the verb, no timeout was added**; and `killable`
  means the kill path has a pane to address, not that the kill will land.
- Also: **`js_syntax_check.py` now needs playwright, as `render_check.py` already did, and neither
  is declared in `pyproject.toml`** — the whole file is behind `importorskip`, so a machine without
  playwright still collects and PASSES.

## `guard_observations` G1/G2 — as previously recorded (now joined by G3, G4 from round 5).

## Other named gaps
- `main` and `integration` have **no common ancestor** (separate roots 8685558 / 22d9ef2). A PR
  needs `--allow-unrelated-histories`. This is the same `commits_behind = 2` that capped every
  round-3 severity at `unconfirmed`.
- **This harness has no `TaskCreate`/`TaskList`/`TaskGet` primitive** — the cc10x task graph is
  tracked in the workflow JSON instead (`task_primitive_unavailable`).
- Appendix A of the spec is stale (C22), doubly so: macOS paths under a Linux target, `repo_id`
  values contradicting D48's worktree binding, and an example row built on `workspace.root_path`,
  which D57 removes.
- `caller_id` is an **unauthenticated self-stamp**, so per-caller scope is expressible but not
  trustworthy.
- **F8 carries into round 5**: AC-21 *printed* the post_milestone count instead of asserting it,
  exiting 0 for any value — and it is the clause that would have caught F4.
- Round 3's teardown was **self-verified rather than asserted**: `ss -ltnp` no listeners, no
  chrome/chromium processes, `/tmp/qa3-*` empty, `git diff --stat -- src/ tests/ tools/` empty,
  no tmux command issued, no `~/.claude/` path touched.
