# QA research lane — source: `cc10x_artifacts` — §2 QA history / per-round defect ledger
wf:wf-20260921T212808Z-9172ed6b · returned 2026-09-22 (chunked hand-back; lane is read-only, router transcribed)

## Yields, verified against the artifacts
| round | recorded yield | evidence |
|---|---|---|
| 1 | 11 defects, FAIL | json:769 "all remediated and verified closed by live driving in run 2" |
| 2 | 2 defects, FAIL | json:774 kill_failures had no reader (HIGH); double-click Create made two projects (MEDIUM) |
| 3 | 3 defects, FAIL | json:789; report-qa3.md:12 "2 of them on ground neither prior run reached" |
| 4 | 6 defects, FAIL | json:809 "all fresh ground; run 3 D1/D2/D3 all re-verified closed. pytest tests/web was 298 passed while all six were live." |

Total recorded: 22. **Evidence is deeply asymmetric — only round 3's three are described anywhere.**

## Round 1 — 11 defects: NOT ENUMERATED ANYWHERE
No `runs/qa1/`. Sole record is json:769. Recorded closed with **no id, no description, no named check**.
=> Round 5 cannot re-verify round 1's closures. This is a real hole in the chain of evidence.

## Round 2 — 2 defects, both closed with a named check
- run-2 d1: `kill_failures` had no reader (HIGH). Closed twice — reader at `#dlg-delete-live`
  (refusal renders "Not stopped, and why: | <ulid> | RunnerRefusal: tmux exited 1", project kept,
  `anomaly.stop_failed`=1) and at `#dlg-delete-outcome` on a real landing (report-qa3.md:184-185).
- run-2 d2: double-click Create made two projects (MEDIUM). Closed — two synchronous `el.click()`
  yield 1 POST, 1 store row, 1 page row (report-qa3.md:186).
`qa-remfix-2` = commit e6adfc1, 3 committed tests, suite 2190 passed/2 skipped.

## Round 3 — D1/D2/D3, full report on disk at runs/qa3/report-qa3.md (HEAD e6adfc1)
- **D1** (HIGH, capped unconfirmed): Projects + Settings unusable across **761-900px**.
  `app.css:2019` inside `@media (max-width:900px)` sets `.herd-col{display:none}`; the `.panes2`
  rescue at `app.css:1935-1936` lives inside `@media (max-width:760px)` so it never applies.
  At 800x900 Projects renders the word DETAIL over an empty pane with **0** clickable controls;
  Settings has 1 (`#settings-back`, which changes nothing). Sibling sweep: 2 of 5 `.herd-col`
  members affected, enumerated from the live DOM not the stylesheet.
  CLOSED — `qa-remfix-3` commit b1c1eb9; `render_check.VIEWPORTS` gains 820; plan rev 6 (83c76b8)
  rewrites AC-28 to name `render_check.VIEWPORTS` rather than restating the widths.
- **D2** (HIGH, capped unconfirmed): on a phone the Projects dialogs open **invisible and trap the page**.
  `projects.js::scaffold` appends `#dlg-project`/`#dlg-delete` as children of `#page-projects`;
  `app.css:1934` `@media (max-width:760px){.panes2[data-level] > *{display:none}}` — an AUTHOR rule
  beating the UA's `dialog[open]{display:block}`. Measured at 390x844: `open:true :modal:true
  display:none box 0x0`, every tap BLOCKED, the only exit a keyboard Escape — on the device the spec
  calls the primary client. Sibling sweep 2 of 3 `showModal()` sites (`#dlg-legend` unaffected,
  declared at shell level). CLOSED — b1c1eb9.
- **D3** (MEDIUM, capped unconfirmed): Flock legend tooltip left on screen swallows the next click.
  `flock.js:301-303` binds focus->showTip and click->openLegendSheet; `<dialog>.close()` restores
  focus, re-firing focus. `.tip` (app.css:833) is `position:fixed; z-index:40; pointer-events:auto`.
  Blocks 2 controls at 1280x900, 4 at 390x844 — including the info button U1 makes the documented
  way in. Single site. CLOSED — b1c1eb9; suite 2197 passed/2 skipped.

**All three D1-D3 severities were capped `unconfirmed`** — explicitly a CONFIDENCE FLOOR, not an
impact level (report-qa3.md:25-30) — because `commits_behind = 2` on the only repo they span.
The three share ONE shape (json:794): *a media query written for one page, naming a class a second
page also uses.*

## Round 4 — D4-D9: ids and one-line subjects only
Sole textual record json:814 — lane A = D4 legend sheet untappable + D5 double click binding +
D8/D9 `.back` sizing; lane B = D6 terminal never fitted + D7 project mutations never publish.
Screenshots with no prose in `runs/qa4/`: s9-terminal-duplicate-line, s10-desktop1440, s10-phone390,
s12-stale-edit, s14-forced-colors, s14-rtl, s19-legend-sheet-390, s3-390-projects-detail,
s3-390-settings-detail. Round 4's brief (json:804): "confirmation of D1-D3 plus untouched ground:
terminal WebSocket, two-tab concurrency, keyboard-only and a11y, width extremes, audit sink".

**ARTIFACT WAS STALE — corrected by the router at round 5 start.** The lane read D4-D9 as
`in_progress` with no check recorded. In fact both lanes completed and merged earlier this session:
lane A = f391020 merged as 037c889 (D4, D5, D8, D9); lane B = 34f4b83 merged as c243773 (D6, D7).
Verified on the merged tree: pytest exit 0, mypy --strict exit 0 (131 files), tests/boundaries
exit 0 (105 rules), js_syntax_check exit 0 (9 files). The lane's reading was correct about the
artifact; the artifact was wrong about the world.

**There is no report-qa4.md, report-qa2.md or report-qa1.md.** `qa.artifacts.*` are all null.
