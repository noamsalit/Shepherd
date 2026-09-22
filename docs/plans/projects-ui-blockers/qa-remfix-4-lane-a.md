# QA remediation, fourth pass — lane A: the sheet with no door, and a chevron with no size

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: qa-executor)
- Base: `b1c1eb9` on `integration`; branch `remfix4-lane-a`
- Lane: **A of two.** Lane B holds D6 (terminal fitting) and D7 (project SSE
  publication) in a separate worktree. The two lanes share only
  `tests/boundaries/consumer_manifest.json`, and this lane changed three digest
  lines in it and nothing else.
- Python: `/root/Shepherd/.venv/bin/python`
- QA drivers reused:
  `scratchpad/qa4/{env,drive,seed,s8_listeners,s15_phonetargets,s19_dialog_sweep}.py`
  (copied to `scratchpad/lane-a/qa4/` with `REPO` repointed at this worktree, so
  the re-runs measure the fixed bytes rather than `integration`'s)
- Files touched: `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/flock.js`, `src/shepherd/web/static/app.css`,
  `tests/web/test_shell_live.py`,
  `tests/boundaries/consumer_manifest.json` (**three digests, no new entry**),
  and this file.
- Before: 2275 collected, 76 live-deselected, 2197 passed / 2 skipped.
  After: **2279 collected, 76 deselected, 2201 passed / 2 skipped** — the four
  new tests and nothing else.

Four defects, three of which turn out to be two causes. D8 and D9 are one
stylesheet rule with two shapes, and D4 is a wiring that was already written
waiting for markup that never shipped.

| # | Sev | Cause | Fix |
|---|---|---|---|
| D4 | HIGH | `<dialog id="dlg-legend">` shipped with no button, and no `closedby` | a `[data-close]` close button — the attribute `flock.js` was already looping over — plus `closedby="any"` |
| D5 | MED | two click bindings for one card: `flock.js`'s own and `app.js`'s delegated one | drop `flock.js`'s, which is the one `index.html` does *not* document |
| D8 | LOW | `.back` had `place-items: center` and no size, so its box was the parent's | give it a size and stop a column parent stretching it |
| D9 | LOW | six controls at 21px tall, below WCAG 2.2 AA 2.5.8's 24x24 | the same `.back` pass, plus `min-block-size` on `.mini-open` |

---

## The seam, and why it is this one

Every assertion below is at the **shipped-shell live seam**:
`tests/web/test_shell_live.py`, which serves the real
`src/shepherd/web/static/index.html` from the shipped `ThreadingHTTPServer`,
lets chromium fetch the real modules, and supplies nothing but the clicks. It
is not marked `live`, so it runs in the default suite.

It is the only seam that can hold these four. D4 is *dismissal*, not markup:
run 3's D2 sweep read `#dlg-legend` as fine because it measured **visibility**,
and a byte-reading test would have made the same mistake in a different
vocabulary. D5 is two handlers on one node, which exists only at runtime. D8
and D9 are computed boxes at 390px. None of them is a fact about a file.

Two harness capabilities were added to `_open()` / `_at()`, both defaulted off
so the eighteen existing tests are byte-identical in behaviour:

- **`touch=True`** — a real touchscreen. `locator.click()` synthesises a mouse,
  and a mouse has a `hover` a finger does not; D4 is precisely a question about
  what a finger can do.
- **`init_script=…`** — a script that runs *before any module of the page does*,
  which is the only way an `addEventListener` spy can see a binding made at
  import time. QA's S8 used the same mechanism and the spy is carried over with
  QA's own probe proof: a planted node with two of its own click handlers and
  one on its parent must read back as three, asserted before any count of a
  real control is believed.

---

## D4 — the explainer sheet could not be closed without a keyboard

**RED, verbatim:**

```
AssertionError: the legend sheet is open and modal at 390px and offers no
visible control that closes it: visibleButtons=[], dataCloseWired=0,
closedby=None — on a phone the only exit is a page reload
```

`dataCloseWired=0` is the whole defect in one number: `flock.js:506-508` loops
over `[data-close="dlg-legend"]` and the attribute existed nowhere in the
document, so the loop was dead code. The sheet opens from the ⓘ **and from all
eight legend keys**, so the entire legend row was a trapdoor.

**Fix.** A `<button class="sheet-close" data-close="dlg-legend">` in
`.sheet-head`. The wiring needed no change — it was correct and unreachable.

**Where I went past QA's shape, and the verification it asked for.** QA asked
whether `closedby="any"` was also warranted and said to verify support rather
than assume it. I did, in this tree's browser, and it is there:

```
chromium version: 153.0.8010.12
supported attr ('closedBy' in dialog): True
after backdrop tap, open: False
```

Both are shipped, deliberately, because they fail differently. The **button**
works in every browser and is what the fix rests on; `closedby` is the
platform's light-dismiss, which is what a phone reader reaches for first, and
in a browser without it the attribute is inert decoration rather than a
regression. The test asserts them separately and the `closedby` assertion is
guarded by an explicit `'closedBy' in d` check whose failure message says that
the button is the load-bearing half — so a future browser dropping the feature
reports the truth instead of reading as a UI defect.

**GREEN, from the re-run of QA's own S19 sweep:**

```
--- dlg-legend ---
  {"open": true, "modal": true, "visibleButtons": [{"text": "Close", "w": 32, "h": 32}],
   "closedby": "any", "dataCloseWired": 1}
  tap the very top of the screen   -> open = False
```

**What S19 also says, and I did not fix.** `#dlg-project` and `#dlg-delete`
have the same absent light-dismiss — three taps outside the box, still open,
only Escape closes them. They are **not** trapdoors: each renders a visible
`Cancel` at 66x35 and 66x28, which is why QA filed D4 and not these. They are
`projects.js`'s, which is outside this lane's file set, and adding
`closedby="any"` to them is a one-attribute change somebody should make
deliberately rather than as a rider on this one. **Recorded, not fixed.**

---

## D5 — one tap on a card ran two handlers

**RED, verbatim:**

```
AssertionError: one tap on a session card runs 2 click handlers, not one:
['BUTTON x1', 'DIV#flock-cards x1'] — the card is opened twice, which is two
attaches against the same tmux pane
```

The chain names both bindings and which file each is in. `index.html:261`
documents the delegated listener on `#flock-cards` as the intended path, so
`flock.js`'s own binding is the redundant half and it is the one that went. I
did not touch `app.js`.

**One thing beyond deleting the line.** `sessionCard(session, view, handlers,
now)` no longer used `handlers`, and neither did `renderCards`, which existed
only to pass it down. Both lost the parameter. The cascade stops there:
`renderFlock(view, handlers, now)` is exported and still needs it for
`renderProjects`, and following it further would have reached `app.js`. An
unused parameter left behind would read, to the next person, as though a
handler belonged here.

**GREEN, from the re-run of QA's own S8 listener sweep** (the same
`add_init_script` spy, the same probe proof):

```
PROBE PROOF (planted 2 own + 1 ancestor): {"total": 3} VERDICT PASS
shepherd   controls=  1 with>1 click handler=0
flock      controls= 14 with>1 click handler=0
queues     controls=  0 with>1 click handler=0
projects   controls=  4 with>1 click handler=0
kanban     controls=  0 with>1 click handler=0
settings   controls= 10 with>1 click handler=0
```

**0 of 29**, from 4 of 29. Single cause, as QA said, and all four were cards.

---

## D8 and D9 — one rule with no size of its own

QA's reading is exactly right and the fix is one pass. `.back` was
`display: grid; place-items: center` with **no width and no height**, so its box
was whatever the parent imposed:

- a flex **row** (`.proj-band`, `.col-head`) collapsed it to its 16px glyph plus
  padding — 21x21, below the 24x24 minimum;
- a flex **column** (`.proj-detail.set-panel`) stretched it to the full 394px,
  and `place-items: center` then put the chevron at x=193, dead centre of a
  390px screen with nothing beside it.

**RED, both, verbatim:**

```
AssertionError: controls below WCAG 2.2 AA 2.5.8's 24x24 minimum at 390px,
where a chevron is the only way out of a drill-down:
["projects/detail 21x21 back 'Back'", "projects/detail 320x21 mini-open 'untitledrunning'",
 "settings/detail 394x21 settings-back 'back'", "flock/detail 21x21 back 'Back'"]

AssertionError: #settings-back is 394x21 inside a 390px DIV.proj-detail set-panel
— a full-width band, and `place-items: center` puts its chevron at x=193 with
nothing beside it
```

(Four rows rather than QA's six because this fixture seeds one project with
three sessions rather than four; every *class* of the six is represented.)

**Fix.** `.back` gets `inline-size: 44px; block-size: 44px; flex: none;
align-self: start`. `.mini-open` gets `min-block-size: 24px`.

**The judgement QA asked me to record: why 44 and not 24.** QA noted that 42
further controls sit between 24 and 44, that those are AA-conformant, and that
the project's own `.nav-item { min-width: 44px }` shows what it aims at. I did
**not** raise those 42 — that is a design pass across every page and would have
been a second change riding on a defect fix. I did take `.back` to 44 rather
than to the 24px floor, for one reason that is specific to it: on a phone the
chevron is the **only** way back out of a drill-down. Everywhere else, clearing
the minimum means a control is reachable; here, missing it means being stuck,
which is the same failure D4 is. The `.mini-open` rows, which have an
alternative (the Flock reaches the same session), get the floor.

**Driven at 390 only**, because QA's note on its own coverage is the reason this
was missed: the chevrons are `display: none` above 760, so the 1280 sweep saw
zero sub-24 targets. The new test walks both drill-down levels of all three
two-pane pages at PHONE width.

**GREEN, from the re-run of QA's own S15 sweep:**

```
  UNDER 24x24 (fails WCAG 2.2 AA 2.5.8 Target Size Minimum):

  between 24 and 44 (45 controls) — AA-conformant, below the 44 the project's own .nav-item sets
```

Empty, from six. The 24–44 band went 42 → 45 as the three `.mini-open` shapes
moved up into it.

Shots: `scratchpad/lane-a/qa4/shots/after-390-{settings-detail,projects-detail,legend-sheet}.png`,
against QA's `runs/qa4/s3-390-settings-detail.png` and `s19-legend-sheet-390.png`.

---

## Gate A — the byte-freeze

Seen red first, naming exactly the three paths this lane changed and no others:

```
AssertionError: files changed under web/ or cli/ since the freeze:
['web/static/app.css', 'web/static/flock.js', 'web/static/index.html']
tests/boundaries/test_consumer_surface_frozen.py:77   EXIT=1
```

All three were **already declared** — `app.css` and `index.html` in
`rebase.regenerated_paths`, `flock.js` in `post_milestone.edits` — so three
digests were refreshed in the `files` block and **no entry was added**. A second
entry for a path already in `regenerated_paths` would break the disjointness the
gate asserts; a second `post_milestone` entry for `flock.js` would break
`len(seen) == len(set(seen))`.

The refresh was line-targeted rather than a `json.dump`, for two reasons. Lane B
edits this same file in another worktree, so every line this lane did not change
stays byte-identical and the merge has nothing to argue about. And `baseline`
carries the same three keys: a whole-file substitution would have rewritten the
step-0b freeze, after which "which digests moved?" is unanswerable — which is
the one question the retained baseline exists to answer. The refresher asserts
it found exactly one line per path **inside the `files` block** and exits
non-zero otherwise; it caught the two-block collision on its first run. It is at
`scratchpad/lane-a/refresh_digests.py`.

Resulting diff: 3 lines changed, 3 lines added, in one hunk.

---

## Exit criteria, each with its unpiped exit code

| Check | Result |
|---|---|
| `pytest -q` (full) | **exit 0** — 2201 passed, 2 skipped, 76 deselected, 520.92s |
| `mypy --strict src/` | **exit 0** — no issues in 130 source files |
| `pytest tests/boundaries -q` | **exit 0** over 105 rules, after being seen **exit 1** on exactly the three changed paths |
| `pytest tests/web -q` | **exit 0** (the regression sweep around the changed modules) |
| D4 / D5 / D8 / D9 | each **exit 1** before its fix with a message naming the real behaviour, **exit 0** after, driven at 390 except D5, whose duplicate binding is width-independent |

`pgrep -f "vitest|jest"` is not applicable; no JS runner is involved.

---

## Unproven, and left that way

1. **`closedby` in browsers that are not this chromium.** Verified at 153 only.
   The close button is why that does not matter, and the test says so in its own
   failure message rather than in a comment.
2. **The two Projects dialogs still have no light-dismiss** (above). Visible
   `Cancel` on both, `projects.js` is not this lane's, recorded not fixed.
3. **The 42 controls between 24 and 44** are untouched and still
   AA-conformant. Whether the project wants 44 everywhere is a design decision,
   not a defect.
4. **D5 was proved at the handler-count seam, not at the `Runner` seam.** QA
   measured `['snapshot', 'attach', 'snapshot', 'attach']` per click; the test
   here asserts that exactly one handler runs, which is the cause rather than
   the consequence. A `Runner`-seam assertion would have been a second, slower
   proof of the same single fact, and the handler count is the one that names
   *which* binding to delete when it goes red again.
5. **No `-m live` lane was run**, per the standing constraint.
6. **`is_mobile=True`** is used by QA's drivers and deliberately *not* by the
   new tests, which use `has_touch` alone so their geometry is comparable with
   the eighteen phone assertions already in the module. The two agree on every
   number reported above.
