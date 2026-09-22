# QA run 4 remediation — lane B

Two defects: **D6**, the terminal emulator was never fitted to the box it was
drawn in, and **D7**, no project mutation ever told a second client. Both were
found by QA run 4, which was the first run with a real browser in it.

Base: `integration` @ `b1c1eb9`. Lane A is fixing four frontend defects in
`index.html`, `flock.js` and `app.css` in a separate worktree; nothing here
touches those three files.

---

## D6 — the emulator is fitted now, and the one thing it still cannot do is on the page

### The decision, and why it is this one

The brief offered three ways to fit and one way to stay honest without fitting.
**The branch taken is: size the emulator from its container, at open and on
every resize, and declare the single residual on the page.** Nothing is
vendored, no route is added, and the pane is not touched.

**Why not `terminal_resize`.** It is the obvious answer — a registered `ToolDef`
at `tools_terminal.py:398` with no entry in `POST_ROUTES`, waiting for a caller
— and it is the only branch that could show a 160-column pane inside a 628px
column, because it makes the pane narrower instead. It was rejected on two
costs:

1. `runner/local.py::resize` runs `tmux resize-window`, which **forces
   `window-size=manual`**, and the module says so on the line: *"a later human
   attach is clipped (E-M3-22)"*. A viewport-driven resize would spend that
   permanently, for every session anybody ever looked at.
2. It makes a **viewport a mutation of the work**. A glance from a phone would
   shrink a running agent's pane to 39 columns, and the agent would keep
   working in it. This page's whole stated position is that there is no path
   from the browser to the pane — `terminal.js` ships `disableStdin: true` and
   renders the reason (T19-c) — and the first thing to travel that path should
   not arrive by accident of window size.

**Why not a fit addon.** `vendor/VERSION.txt` governs `vendor/` and governs it
tightly: a closed, machine-checked claim list, a digest per file recomputed on
every run, and a recorded note that the integrity check is two endpoints of one
CDN agreeing rather than a signature. Adding a file there is a real cost, and it
buys an algorithm that is about fifteen lines — which are now in `terminal.js`,
using only `term.resize`, `term.cols`, `term.rows` and the rendered box. No
private API, no new bytes under `vendor/`, `VERSION.txt` untouched.

**Why the page still says something.** The fit closes the clipping completely
and closes the wrapping *only where the window is wide enough*. At 2560 the
terminal gets 223 columns and the 160-column pane is shown whole; at 1440 it
gets 80 and the pane's lines are re-wrapped. That residual is stated on the
page in `FIT_LIMITATION`, beside T19-c's sentence, in the slot that already
carries one. QA's framing was that **the silence is what makes it a defect**,
and the absent fit is no longer silent in either direction: it does as much as
it can and says what it cannot.

### Measured, before and after

Same fixture pane as run 4 — `LIVE_FIELDS` is `160|45` — same three viewports,
same page, real chromium, shipped server. Taken by
`tests/web/test_terminal_fit_live.py`, which is committed, so these numbers are
re-runnable rather than transcribed.

| | 390x844 | 1440x900 | 2560x1440 |
| --- | --- | --- | --- |
| **before** host client width | 356 | 628 | 1748 |
| **before** host scroll width | 722 | 722 | 722 |
| **before** unreachable px | **366** | **94** | 0 |
| **before** emulator | 80x24 | 80x24 | 80x24 |
| **after** host scroll width | 356 | 628 | 1748 |
| **after** unreachable px | **0** | **0** | **0** |
| **after** emulator | 45x23 | 80x30 | **223**x62 |
| **after** screen right edge | 369 (in 390) | 1421 (in 1440) | 2540 (in 2560) |

The 366 is run 4's own number, reproduced. The 1517 it reported at 1440 is the
same fact read off the right edge; it is 1421 now, inside the window.

At 2560 the fit shows **223 columns for a 160-column pane** — the whole pane
width, which the old 80 never could at any size. `test_a_wide_enough_window_
shows_the_whole_pane_width` asserts it, and its sibling asserts the residual
still bites at 1440, so neither half of the claim is left to a reader's charity.

### Two defects I introduced and found, both worth writing down

Both were found **by measuring**, and both would have passed a source review.

1. **A 307 418 px container.** The first build measured rows from
   `el.clientHeight`. `#session-terminal` is `flex: none; min-height: 12rem`
   with no height of its own, so its height *is* whatever the emulator draws:
   rows grew the box, the box grew the rows, and the `ResizeObserver` rode the
   loop. **Every test still passed**, because assertions of the form "the
   content fits inside its box" are vacuous for a box that grew to fit the
   content. The guard is now explicit — `hostClientH <= 4 * viewportH` — and it
   is in the test because the vacuity, not the loop, is the reusable lesson.
2. **A fit that never converged.** The ruler `<span>` measures a line box of
   14.95px where xterm's own cell is 17px. Using the ruler for the target and
   the drawn box as a one-shot correction meant, at 390, an estimate of 26 rows
   cut to 23, then re-estimated at 26 by the next observer callback. The page
   was measured mid-swing: `renderedRows 23` against `declaredRows 26`. The fit
   now prefers xterm's own drawn metrics wherever they exist and loops until it
   agrees, so it is **idempotent** — which is the property a resize observer
   needs from the thing it calls, and which nothing in the first build had.

### What D6 does *not* prove

- **G-M3-6 is narrowed, not closed.** The box the bytes are drawn in is now
  measured. That xterm draws the *glyphs* identically to a real terminal is
  still unverified, and `terminal.js` says so in its head.
- **Three viewports, not the full sweep.** `tools/render_check.py::VIEWPORTS`
  declares six, including the 820x1180 tablet QA run 3 added. This module drives
  the three run 4 named.
- **The re-fit on resize is wired but not driven by a test.** The
  `ResizeObserver` is installed and disconnected with the socket; no test
  resizes a window and re-measures. The idempotence that makes it safe is
  argued in the source and exercised only incidentally (the observer fires
  during the initial layout in all nine passing cases).
- **`top` is sampled once per open.** Content appearing *above* the terminal
  after it opens — a long `next_actions[]` list arriving late, say — will not
  re-budget the rows. It is the price of not being circular, and it is untested.
- **`app.css` is untouched**, including `#session-terminal { overflow: hidden }`
  and its `min-height: 12rem`. That file is lane A's. The fit makes the clip
  vacuous rather than removing it; a container with a real height would let the
  terminal be taller, and that is a layout decision for whoever owns that file.
- **`terminal_resize` is still a registered tool with no route and no caller.**
  Deliberately, per the decision above. It stays a known unwired capability.

---

## D7 — six mutations, and a second client that now hears all six

### What was wrong

Structural: `register_project_tools(*, store, kill, now)` had **no publish
parameter at all**, so there was nothing for a harness to stub and nothing for a
page to hear. Run 4 enumerated all sixteen `POST_ROUTES` first, drove the six
project mutations, and counted the frames a second client received on
`/api/events`: six 200s, zero frames — with a `publish()` probe on the same
reader proving the reader was live, so every zero was a real zero.

### What was built

A third module in the family, `toolsurface/tools_projects_events.py`, holding the
one rule that decides whether anything happened: **the record's own positive
key**. `create_project` sets `created`, `rename_project` sets `renamed`, and so
on through `described`, `deleted`, `added`, `removed` — and the event kinds are
named from those same words, so the name of the event and the field that gates
it cannot drift apart:

| tool | kind | gate |
| --- | --- | --- |
| `create_project` | `project.created` | `created` |
| `rename_project` | `project.renamed` | `renamed` |
| `set_project_description` | `project.described` | `described` |
| `delete_project` | `project.deleted` | `deleted` |
| `add_repo` | `project.repo_added` | `added` |
| `remove_repo` | `project.repo_removed` | `removed` |

`noun.pastverb` is the vocabulary already in the ring — `session.spawned`,
`session.killed`, `session.interrupted`, `session.classified` — not a second one
invented for projects. The brief asked for `session.changed` and its siblings;
there is no `session.changed` in this tree, and the siblings are these.

`project_id` rides in the **payload**, because `StreamEvent` carries only
`session_id`; `web/sse.py::envelope` already promotes `project_id` out of the
payload into §12's envelope, so a browser reads it at the top level and this
layer never learns what SSE is.

The announcement **wraps** each handler in `build_project_tools` rather than
living inside it, so the handlers stay what the family docstring says they are —
arrange arguments, call one store verb, project the record — and stay callable
by a test that does not care about the ring. `build_delete_tool` takes the
announcer as an argument, which is the direction that keeps the split acyclic.

**A refusal announces nothing.** A producer that fires on every call teaches the
page that an envelope means a change and then lies about it, and the only thing
a stale tab could do with the lie is re-read a tree that is identical.
`test_a_refused_mutation_tells_nobody` holds that, and it holds it by *waiting*
for a frame that does not come rather than reading too early.

`publish` is **required with no default** on `register_project_tools`, on the
same terms as `kill`: `build_project_tools` may default it to
`drops_every_event`, because a caller that only wants to read the schemas has no
ring — but a composition that forgot would be silent in exactly the way D7 was,
and mypy refuses the omission instead.

### Proved at the wire

`tests/web/test_projects_stream.py`. Every assertion crosses two real sockets:
the POST through the real handler, and a second client reading `/api/events`
with `Last-Event-ID: 0`, which is the replay path a tab that connected a moment
earlier would have taken. `tests/web/conftest.py` now injects the **real ring**
rather than a recorder, because the defect is about a second client and a double
would move the assertion back to the seam that never saw it.

Run 4's own discipline is kept as a test: `test_the_reader_is_not_blind`
publishes one event directly and reads it back over the same path, so a `0`
anywhere else in that file is a real `0`.

### `set_autonomy_level`: out of scope, and still silent

QA's caveat was respected and the answer is **not fixed here**. It lives in
`tools_master.py`, which is not in lane B's file set, and QA's own reading is
that its impact is lower — Settings reacts only to a `GAP` envelope by design.
It remains a seventh silent mutation. It is not fixed and it is not hidden.

### What D7 does *not* prove

- **The proof is at the HTTP/SSE wire, not at two live browser tabs.** Run 4's
  `s11_twotabs.py` drove two real chromium contexts against one server; that
  driver is not committed, and the committed proof is a second HTTP client on
  the real stream. The consumer side — that `app.js::refreshAll()` really
  re-renders tab A on receipt — is asserted by its existing tests and by the
  comment at `app.js:279-282`, not re-proved here.
- **Ordering and coalescing under concurrency are untested.** The ring is
  `ADR-7`'s and has its own tests; nothing here drives six mutations at once.
- **`remove_repo` publishes on `{"removed": true}`**, which is what the verb
  answers; it carries no `refused` string, so a removal of a repo that was not
  there is a `False` and announces nothing, which is correct but is the one verb
  in the family whose record shape is not the family's.

---

## The gates

| check | result |
| --- | --- |
| `pytest -q` | see the run below |
| `mypy --strict src/` | exit 0, 131 files (130 + `tools_projects_events.py`) |
| `pytest tests/boundaries -q` | exit 0 over 105 rules, **after** being seen red naming exactly `web/static/session.js` and `web/static/terminal.js` |

**Gate A, per path.** `web/static/session.js` was already declared in
`post_milestone.edits`, so it got a **digest refresh only, no second entry**.
`web/static/terminal.js` was in neither list, so it got one new entry and a
digest refresh. `web/routes.py` is untouched — the `terminal_resize` route was
considered and rejected, so the table did not move. The edit was made as a
surgical text replacement rather than by re-serialising the JSON, so every line
lane A does not own is byte-identical and the two lanes merge on the lines each
actually changed.

## Files

- `src/shepherd/toolsurface/tools_projects_events.py` — new; D7's producer.
- `src/shepherd/toolsurface/tools_projects.py` — wraps six handlers; `publish`
  required at registration.
- `src/shepherd/toolsurface/tools_projects_delete.py` — takes the announcer.
- `src/shepherd/toolsurface/compose.py` — injects `_publish`, the same adapter
  M3's set and the approval store already get.
- `src/shepherd/web/static/terminal.js` — D6's fit.
- `src/shepherd/web/static/session.js` — the second declared limitation.
- `tests/web/test_projects_stream.py` — new; D7 at the wire.
- `tests/web/test_terminal_fit_live.py` — new; D6 by measured geometry.
- `tests/web/conftest.py`, `tests/web/test_session_wiring.py`,
  `tests/web/test_projects_page.py`, `tests/toolsurface/test_tools_projects.py`,
  `tests/toolsurface/test_tools_m3.py`, `tests/toolsurface/test_compose_m4.py` —
  call sites, and the capped-module count admitting the new module.
- `tests/boundaries/consumer_manifest.json` — two digests, one declaration.
