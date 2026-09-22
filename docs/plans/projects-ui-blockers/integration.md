# The integration pass — four pages, one shell, and the first time any of it ran

Branch: `integration`, main checkout.
Merged, in order: `worktree-agent-aff252e79c236746a` (Phase 6),
`worktree-agent-a21a53a6da5bbc6ce` (Phase 7),
`worktree-agent-a731892fccd97a8dc` (Phase 9).

**The headline: four pages built contract-first in four worktrees, and every
line of their JavaScript had been proved by byte scans and a harness that loads
no module. Executing it for the first time found five defects, three of them in
the shipped page and one of them older than this milestone.** None of them was
visible to any check that existed.

## The five the live drive found

| # | Defect | What could not see it |
| --- | --- | --- |
| 1 | `app.js` handed the **whole `get_session` envelope** — `{found, session, subagents}` — to `renderSession`, so every field read `undefined` and `openTerminal` opened a socket at `/api/sessions/undefined/terminal`. **This predates the redesign**: the shipped `app.js` did the same thing. | Every scan of `session.js` was correct about `session.js`. Nothing had ever *called* `renderSession`, so the caller's shape was never checked against the route's. |
| 2 | `.herd` declared **two** grid rows (`auto minmax(0, 1fr)`) and now has three full-width items: the legend, the stop-summary band, and the panes. The stop band took the flexible row and **the three columns were pushed off the bottom of the screen**. | `render_check.py` reported *12 pages · 0 failures* over it: nothing overflowed horizontally, no console error was raised, and every `must_see` string was still in the DOM. It took looking at the screenshot. |
| 3 | `.detail` is used twice — as the Flock's third pane (a **grid** item) and as the Shepherd page's root (a **flex** item) — and carries no `flex: 1`. Every other page root does. **The composer was not pinned to the bottom**; the conversation sat in a content-height box at the top of an empty column. | Same as #2. The page named itself, nothing threw, nothing overflowed. |
| 4 | `.set-panel { display: flex }` is declared **155 lines below** the phone drill-down's `.panes2 > *` at equal specificity, so it won on source order: **Settings showed its nav and its panel stacked at 390px**, with a back chevron in the middle of the page and nothing to go back from. Projects, whose panel carries no second class, was fine. | A rule one page silently outranks. The Projects page passed the same check. |
| 5 | The harness carried `#flock-heading` **inside `#flock-legend`** — the element `flock.js::renderLegend` calls `replaceChildren()` on. It satisfied `render_check` only because the harness runs no module; the shipped page would have deleted the page's own name on its first render. | A fixture that loads no module cannot see what a module deletes. |

Each one now has a test that fails if it returns, and each test says which
observation it is (bytes, or pixels in a 390px browser).

## The defect the task named — principle 5 on a phone

`#stop-summary` carried `class="legend-note"` in the harness, and
`app.css:1587` was `.legend-note { display: none }` below 900px. The unknown
rate, the low-confidence count and the never-classified count were therefore
**absent on the primary client**, on the one page root that ships visible.

The strip has its own class now — `.stop-summary`, spanning the grid like
`.legend` above it — rather than an exemption written into a decorative one.
`.legend-note` had exactly one user, and it was the wrong user, so the rule is
gone rather than left as dead CSS. `#flock-heading` moved into that band: it is
the one strip present at every level of U9's drill-down and at every width, and
nothing clears it. It carries `text-transform: none`, which is load-bearing —
`inner_text()` returns transformed text and the band is uppercase.

Two tests, at two seams:
`test_shell.py::test_the_stop_summary_strip_is_not_a_decorative_note` (bytes: no
rule anywhere in the file hides it) and
`test_shell_live.py::test_the_stop_summary_survives_a_phone` (pixels: the strip
**and all three values** are visible with a non-zero box at 390×844).

## The two debts, closed

Both lists are empty and both pinning tests are deleted, which is what they
existed for.

* **`PENDING_SHELL_WIRING`** — it existed twice after the merge, once from
  Phase 7 (`settings.js`) and once from Phase 6 (`app.js`), the second shadowing
  the first at module scope. Both are gone with
  `test_the_pending_wiring_list_is_exactly_what_is_owed` and
  `test_the_pending_shell_wiring_is_exactly_what_is_owed`.
* **`STALE_SPECIFIERS`** — gone, and so is the branch in `reachable_modules`
  that skipped it. A specifier naming a file that does not ship is now a hard
  failure again, which is the state the list was a temporary exception to.

`shipped - reached` is back to `set(UNREACHABLE_BY_DESIGN)` — `escape.js` alone.

**And the reason the second list mattered, which is the reusable part.**
`flock.js` was *reached*: `session.js` imports `element` and `showLevel` from
it and `session.js` is on the graph. So the module-graph walk was satisfied —
and the page still never drew, because the bootstrap called a `render` it had
imported from a module that no longer shipped. **Loaded is not driven**, and a
walk structurally cannot see the difference: it answers *did the browser fetch
this file*, not *does anything call it*. The half that can see it is an
assertion on `app.js` itself, and it is now
`test_the_bootstrap_drives_every_page_it_loads`: per page, the specifier must be
imported **and** every entry point applied, with `test_the_driving_check_bites`
as its negative control (an imported-but-uncalled `mountFlock` and a called one,
one pair of parentheses apart).

## The shell contracts, honoured, with one departure

Phase 6's, Phase 7's and Phase 9's contracts are met as written, with one
deliberate exception, stated rather than absorbed.

**`#page-projects` ships empty (T9.1 point 1), so it cannot carry its own name
in static markup**, and `test_each_page_root_renders_its_own_name_inside_itself`
reads bytes. The rule now excludes `projects` **by name, with the reason, and
with the exclusion asserted to be currently earned**: the root really is empty,
and `projects.js` really does supply the name. The claim itself is not dropped —
it moves to the live check, which is the only seam that can see a name a module
draws. The shell's two dialogs (`#dlg-project`, `#dlg-delete`) are deleted from
`index.html` for T9.1's reason: a second element with each id, outside the root
the page clears, is the one `getElementById` hands back.

`projects.js`'s list head changed from `.col-head` to `.proj-band` /
`.proj-title` — the same transform that caught T7.2 on Settings.
`inner_text()` read `PROJECTS` and reported the page as unnamed. That is the
one edit to a page module this pass made outside the shell, and it is the
finding T7.1 wrote up for exactly this.

## The rule derived from `index.html`, not typed into it

`test_the_shell_ships_every_slot_the_page_modules_reach_for` derives what the
shell owes from **the modules themselves** — every `getElementById("…")`,
`slot("…")` and `fill("…")` in `flock.js`, `session.js`, `chat.js`,
`settings.js` and `projects.js`, minus every id that module mints — and compares
it with the ids in `index.html`. A list typed twice is a list that drifts; this
one cannot. Arrival is asserted per module at real sizes (session.js's fourteen
is an equality), so a regex that quietly stopped matching fails rather than
reporting a clean shell. `projects.js` is asserted to owe **exactly**
`{"page-projects"}`, which is T9.1's contract stated as a number.

## The manifest — once, and the arithmetic

```
moved (baseline -> files)   11
rebase.regenerated_paths     5   web/routes.py, app.css, app.js, chat.js, index.html
post_milestone.edits         6   rail.js (T5.4) · fleet.js · flock.js · session.js
                                 · settings.js · projects.js
intersection                 0
equality                  moved == rebased | post_milestone   ✔
```

`fleet.js` is declared as a **removal** and `flock.js` as an **addition** —
a rename is two entries, because the manifest is keyed by path and a path that
stopped existing is a move the gate must see. `session.js` is a baseline path
outside `regenerated_paths`, so it is declared rather than re-based. `app.css`,
`app.js`, `index.html`, `chat.js` and `web/routes.py` are digest updates only;
adding a `post_milestone` entry for any of them fails the disjointness
assertion.

**A11 holds and the count is six, not seven.** `sse.js`, `terminal.js`,
`escape.js` and `vendor/*` are byte-identical to the baseline, verified against
the manifest's own digests, and `web/server.py` is byte-identical too.

## The mutation run — eight planted, eight red, one survivor closed

Committed first, planted, reverted with `git checkout -- <path>` (the tree was
committed, which is the whole reason that command is safe here). Every planted
edit is markup, CSS or a call site — nothing that leaves the process.

| # | Planted | Red at |
| --- | --- | --- |
| M1 | `.stop-summary { display: none }` below 900px | the byte test **and** `test_the_stop_summary_survives_a_phone` |
| M2 | `app.js` imports `mountSettings` and never calls it | `test_the_bootstrap_drives_every_page_it_loads` |
| M3 | `#dlg-project` back in the shell | `test_the_projects_root_ships_empty` |
| M4 | `#shepherd-status` dropped from `index.html` | `test_the_shell_ships_every_slot_the_page_modules_reach_for` |
| M5 | `.herd` back to two grid rows | **survivor** — see below |
| M6 | `.panes2 > *` back at its old specificity | `test_the_two_pane_pages_drill_down_on_a_phone` |
| M5b | M5 again, after the survivor was closed | `test_each_page_root_fills_the_column_it_is_given` |
| M7 | `.main > .detail` loses its `flex: 1` | `test_each_page_root_fills_the_column_it_is_given` |
| M8 | `renderSession(answer)` — the envelope again | `test_a_card_click_opens_the_session_pane` and the Projects-link test |

**M5 survived, and it is the one worth reading.** Reverting the grid fix turned
nothing red but the byte-freeze digest — which any change to any byte trips, and
which says nothing about the page. The whole suite, plus `render_check.py`'s
twelve pages, was blind to a Flock whose three panes were off the bottom of the
screen. `test_each_page_root_fills_the_column_it_is_given` closes it by
**measuring** the panes and the composer against the viewport, and M5b and M7
re-plant both original defects against it: both red.

## Checks

Every exit code below was read from an **unpiped** run.

```
.venv/bin/python -m pytest tests/web tests/boundaries -q        exit 0
.venv/bin/python -m pytest -q                       (whole)    exit 0
.venv/bin/mypy --strict src/shepherd                            exit 0  · 130 files
.venv/bin/python tools/js_syntax_check.py .../static/*.js       exit 0  · 9 files, 0 failures
.venv/bin/python tools/render_check.py --file .../shell_harness.html
                                                                exit 0  · 12 pages, 0 failures
git status --porcelain docs/probes/                             empty
git diff --stat src/shepherd/web/server.py                      empty
git diff --stat .../sse.js .../terminal.js .../escape.js .../vendor/   empty
```

**The live drive — the shipped `index.html`, a real `controld` on loopback:**

```
controld: http://127.0.0.1:38029
seeded project=01M3492Z6VKQA34XZRPBQ7Z34T session=01M3492Z70YVPB5VGN1ZAR5G1J
12 pages checked · 12 screenshots · 0 failures                  exit 0
```

`controld.start(host=…, port=0)` with an injected throwaway `HostPlatform`, a
real store, a real route table, real rows, the shipped page fetched from `/` and
the modules fetched from `/static/`. Twelve screenshots at 390×844 and
1280×900 were **looked at**, which is how defects 2, 3 and 4 were found; three
of the twelve are the evidence for the fixes.

Seven committed live tests carry the same claims into the suite
(`tests/web/test_shell_live.py`), skipping rather than failing where chromium is
absent.

## What this does not prove

Not a phone's real browser, not a tunnel, not a slow network: six pages at two
viewports in headless chromium on this host. Not Phase 10 — `tests/web/
test_render_live.py` and the human look at the twelve screenshots are T10.1's
and are not written here. Not the terminal: `openTerminal` now receives a real
session id, and no test drives an *owned* session's WebSocket from the shipped
page. Not the Shepherd conversation against a real master. And not the
`#session-*` pane's styling — the fourteen slots moved into `.col-detail`
unchanged, as the task directed, and `app.css` defines no `.session-*` rule, so
that pane renders unstyled until somebody owns it.

## One note for whoever runs the live drive next

The abstract socket budget is 107 bytes and the scratchpad path alone is 88, so
`controld` refuses to start with `XDG_RUNTIME_DIR` inside it
(`SocketPathTooLong`). The driver points **only** the runtime dir at a short
throwaway; the data and config dirs stay in the scratchpad, and the assertion
that every resolved directory is inside one of the two is kept.
