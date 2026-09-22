# QA remediation, third pass — three defects in one stylesheet, and the width no gate drove

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: qa-executor)
- Base: `e6adfc1` on `integration`
- Python: `/root/Shepherd/.venv/bin/python`
- QA report: `.cc10x/qa/wf-20260921T212808Z-9172ed6b/report.md`
- Files touched: `web/static/app.css` (all three defects), `tools/render_check.py`,
  `tests/web/test_shell_live.py`, `tests/tools/test_render_check_args.py`,
  `tests/web/test_render_live.py` (the third place `12` was a literal),
  `src/shepherd/orchestration/lifecycle.py` (one comment),
  `tests/boundaries/consumer_manifest.json` (**one digest, no new entry** — see
  Gate A below) — and this file.
- Before: **2192 collected, 76 live-deselected, 2190 passed / 2 skipped**,
  `mypy --strict src/` clean over 130 files, 105 boundary rules green.

All three defects were in `app.css`, and none of them was in a rule that was
wrong about the page it was written for. Each was a rule that **did not say
which page it was for** and therefore reached a second one:

| # | Sev | The rule | Who else it hit |
|---|---|---|---|
| D1 | HIGH | `@media (max-width: 900px) { .herd-col { display: none } }` — the Flock's drill-down | the Projects list column and the Settings nav column, 761–900px inclusive |
| D2 | HIGH | `@media (max-width: 760px) { .panes2[data-level] > * { display: none } }` — the phone drill-down | the two `<dialog>`s `mountProjects()` builds inside that root |
| D3 | MED | `.tip { position: fixed; z-index: 40 }` — a hover tooltip | every control under its 19rem box, after `dialog.close()` restored focus and re-fired `showTip` |

---

## D1 — scoped to `.herd`, which is what QA suggested, plus one QA did not

**Fix.** Every selector in the `max-width: 900px` block is now scoped to
`.herd`: `.herd .herd-col { display: none }` and `.herd .back { display: grid }`.

QA offered two shapes — scope the rule, or add a `.panes2 .herd-col { display:
flex }` rescue for 761–900 — and named the first as the one whose selector says
what it means. Taken, for the reason QA gave and one more: a second rescue
would have fixed exactly this 140px while leaving the Flock's rule still
claiming every `.herd-col` in the document, so the next page to reuse the class
rediscovers this defect. Scoping retires the class of bug, not the instance.

**Where I went further than QA's shape.** `.back { display: grid }` was in the
same block and was equally unscoped — and it was **load-bearing for the pages
it was not written for**: the phone drill-down's back chevron on Projects and
Settings had no rule of its own and was relying on the Flock's block, 160px
outside where either page wants it. Scoping `.back` alone would have deleted
the phone's only way back. So the chevron is declared where it belongs,
`.panes2 .back { display: grid }` inside the `max-width: 760px` block, and the
761–900 band no longer offers a back chevron beside a list the reader never
left. Both directions are asserted, and the `.back` half was seen red on its
own (the reverted-selector reading is in the evidence table below).

**Not scoped:** `.legend` and `.herd { grid-template-columns }` in the same
block. `.legend` exists only inside the Flock, so its selector is not lying;
scoping it would be churn in a diff whose whole subject is rules that reach too
far. Recorded so the omission is a decision rather than an oversight.

## D2 — dialogs exempted, not relocated

**Fix.** `.panes2[data-level] > *:not(dialog) { display: none }`.

`index.html:388` records why the two Projects dialogs are built inside
`#page-projects`: `mountProjects()` builds them there, and a second copy
declared at shell level would be the one `getElementById` hands back. Read
before deciding, as instructed. It still holds, so the dialogs are exempted
from the blanket hide exactly as QA suggested. A closed dialog is still hidden
— by the UA's `dialog:not([open])`, which is what should have been hiding them
all along; the author rule was hiding the open ones too, and an author
`display: none` beats the UA's `dialog[open] { display: block }`.

`#dlg-legend` is unaffected and was already fine: it is declared at shell
level, outside every page root, which is 1 of the 3 `showModal()` sites.

## D3 — `pointer-events: none`, and deliberately **not** a second `hideTip`

**Fix.** `.tip { pointer-events: none }`.

QA offered `pointer-events: none` *and/or* suppressing the re-show on the focus
`dialog.close()` restores, and asked whether the first alone is enough. It is,
and the second is not wanted:

- The re-show is *correct*. `close()` really does return focus to the key that
  opened the sheet, the key really is focused, and a tooltip for a focused
  control is what a tooltip is for. Suppressing it would mean a keyboard user
  who closes the sheet is returned to a control whose description has been
  deliberately withheld.
- The tip carries no control of its own — a mark, a label and two paragraphs —
  so nothing inside it wants a pointer.
- It leaves with the focus it follows. The tap that used to be swallowed now
  reaches the control underneath, which blurs the key, which removes the tip.
  That second half is asserted rather than reasoned:
  `document.activeElement.blur()` → `.tip` count 0, at all three widths.

What is *not* claimed: no `touchstart` path was driven (the same gap QA
records). The events are synthesized pointer events that focus the button,
which is what a tap does.

## The reusable finding — a third width, and a gate that has to run it

`tools/render_check.py`'s `VIEWPORTS` was `[("phone", 390, 844), ("desktop",
1280, 900)]`, and **every** browser-driving test either read those two or
re-spelled them. D1 lived strictly between them. Three changes:

1. `VIEWPORTS` gains `("tablet", 820, 1180)` — iPad portrait, inside the dead
   band — with the reason written at the definition site.
2. `tests/web/test_shell_live.py` no longer re-spells the widths under a
   comment claiming it reads them. It derives `VIEWPORTS` through
   `render_check_constant("VIEWPORTS")` and `PHONE`/`DESKTOP` from that
   mapping, and both new sweeps are `@pytest.mark.parametrize`d over its keys —
   so a width added at the one definition site is driven without this file
   being edited. Its `_nav` helper also had QA's own off-by-one (`width < 760`
   against an inclusive `max-width: 760px`); latent while only 390 and 1280
   were driven, a real bug the moment the helper is handed a new width.
3. `tests/tools/test_render_check_args.py` counted `2` reports and `12` pages
   as literals, and `tests/web/test_render_live.py` counted `12` once more —
   the other half of why a width could be added without any gate noticing
   whether it ran. They now count `len(rc.VIEWPORTS)` and `len(rc.PAGES) *
   len(rc.VIEWPORTS)`, with a `len(rc.VIEWPORTS) >= 3` floor so removing the
   tablet again is a red test and not a quiet edit. Both gates report **18
   pages checked · 18 screenshots**. The third literal was found by the full
   suite going red, not by reading — recorded because it is the measure of how
   many places that number had been written down.

**Proved that it bites:** the 820 sweep was red on D1 before the fix and green
after — the reading is in the table below, and the message names the behaviour
("the list column computes display:none and the page offers 0 usable
controls"), not a missing symbol.

## Carried-forward item — the comment, corrected; no reaper built

`lifecycle.py`'s `KILL_RECORD_PREFIX` said the record is *"cleared once the
kill is accounted for"*. It is not: `set_app_state(key, None)` is an `INSERT …
ON CONFLICT DO UPDATE` over `json.dumps(None)`, so the row survives holding the
string `null`. The comment now says *overwritten with `null` — never cleared*,
and that the row survives unread and unreaped.

**Three lines, and it points here for the rest.** The first draft was eighteen
and it turned `test_the_module_stays_inside_its_stated_size` red: ADR-1 caps
that module at 250 lines and it sits at exactly 250 with this comment in it.
The cap is an architectural decision and not mine to spend, so the measurement
(nothing reads the namespace — 4 `KILL_RECORD_PREFIX` hits in `src/`, all
writes; `grep "DELETE FROM app_state" src/` exits 1; a project delete leaves
rows keyed by ids with no session) lives in this file, which the comment names.

**No reaper, as instructed.** My view, recorded because the task asked for it:
one is **not** warranted yet. `get_app_state` answers `None` for absent and for
`null` alike, so there is no behaviour to fix; the growth is one row per
session ever killed, which is the same shape as `ask_fork.*`, and that
namespace grows deliberately (`core/anomalies.py:88`). If a reaper is ever
built it should cover both and arrive with a decision about what evidence is
allowed to expire — not as a side effect of a docstring nobody checked.

**Unproven, and structurally so.** The corrected sentence carries no test. The
difference it describes — a row present holding `null` versus no row — is not
observable through any verb on `Store`; `get_app_state` collapses them and
there is no `app_state` enumerator except `list_anomaly_counts`. The only test
that could see it would open the sqlite file directly, which is the boundary
`tests/boundaries/test_storage_boundary.py` exists to hold. Left as a comment
backed by QA's measurement rather than by a gate.

## Gate A — the byte-freeze

All three fixes are in one shipped file. `web/static/app.css` is already in
`rebase.regenerated_paths`, so **the digest was updated and no second entry was
added** — neither a new `regenerated_paths` member nor a `post_milestone.edits`
entry, which would have put one path in both blocks. `flock.js`, `projects.js`
and `index.html` were not touched at all: D3's fix is CSS, not the JS QA's
shape pointed at.

Seen red before the refresh, naming exactly the changed path:

```
tests/boundaries/test_consumer_surface_frozen.py::test_completing_l4_changed_no_consumer_byte
AssertionError: files changed under web/ or cli/ since the freeze: ['web/static/app.css']
```

## Evidence — every reading, with its unpiped exit code

| what | command | exit |
|---|---|---|
| D1 red at 820 (Projects) | `pytest tests/web/test_shell_live.py -k declared_viewport` → *"projects at 820px: the list column computes display:none and the page offers 0 usable controls [] — 'New project' is not one of them"* | 1 |
| D1 red at 820 (the `.back` half, selector reverted in place, then restored) | same node id → *"settings at 820px: both panes are on screen and a back chevron is offered anyway"* | 1 |
| D1 green, all three widths | `pytest tests/web/test_shell_live.py::test_both_two_pane_pages_can_be_navigated_at_every_declared_viewport` | 0 |
| D2 red at 390 | `pytest …::test_the_projects_dialogs_are_on_screen_on_a_phone` → *"#dlg-project at 390px: showModal() ran and the dialog computes display:none at 0x0 — the modal is open, invisible, and its backdrop is swallowing every tap"* | 1 |
| D2 red again, against the **final** test text (fix reverted in place, then restored) | same node id, same message | 1 |
| D2 green | same node id | 0 |
| D3 red, all three widths | `pytest …::test_the_legend_tooltip_never_swallows_a_click` → *"the legend tooltip at 390px is still on screen after the sheet closed, and a tap at its centre lands on tip-body: every tap inside {…304x149…} is swallowed"* (and the same at 820 and 1280) | 1 |
| D3 green | same node id | 0 |
| the tool's own gate at three widths | `pytest tests/tools -q` → *"18 pages checked · 18 screenshots · 0 failures"* | 0 |
| Gate A red on exactly the changed path | `pytest tests/boundaries -q` (before the digest refresh) | 1 |
| Gate A green | `pytest tests/boundaries -q` | 0 |
| types | `mypy --strict src/` → *"no issues found in 130 source files"* | 0 |
| boundary rules | `pytest tests/boundaries` → *"105 passed"* | 0 |
| the suite | `pytest` → *"collected 2275 items / 76 deselected / 2199 selected … 2197 passed, 2 skipped"* — the baseline's 2192 selected plus this pass's **seven** new tests (3 × D1, 1 × D2, 3 × D3), nothing else moved | 0 |

## What remains unproven

- **`tests/web/test_projects_page.py` and `tests/web/test_settings_live.py`
  still spell `{390, 844}` and `{1280, 900}` as their own literals.** They are
  page tests, not width sweeps, so they were left; the sweep that covers the
  band is the shell's. The drift they represent is real and is the same shape
  that hid D1 — named here rather than fixed, because widening two more files
  was not this remediation's scope.
- **Nothing above 1280 or below 390**, as in QA's own run. The sweep now has
  three points inside that range, not a continuum; 761 and 900 themselves (the
  band's edges) are reasoned from the media query, not driven.
- **No touch events.** D3's phone half is synthesized pointer events.
- **`prefers-reduced-motion`, forced colors, zoom and RTL** — untouched, as in
  QA's run.
- **The `kill.<id>` row's survival** is QA's measurement, not a committed test.
  See the carried-forward section for why one cannot be written at the store's
  seam.
