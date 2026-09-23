# QA run 3 — Shepherd web UI, branch `integration`, HEAD `e6adfc1`

- Workflow: `wf-20260921T212808Z-9172ed6b`, phase `qa-execute`
- Measured: 2026-09-22, repo `/root/Shepherd`, branch `integration`, sha `e6adfc1`,
  `git rev-list --count HEAD..main` = **2**, `git status --porcelain` over
  `src/ tests/ tools/` = empty (clean)
- Env: real `ThreadingHTTPServer` on an ephemeral loopback port, serving the
  **shipped `index.html`**, backed by a real sqlite store in a temp dir, driven
  by headless chromium (playwright). No tmux. No `pytest -m live`. No forks.
- Scratchpad: `/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/qa3`

**Verdict: FAIL — 3 defects, 2 of them on ground neither prior run reached.**

---

## 1. Failure classes

| class | count |
|---|---|
| `missing-input` | 0 |
| `wrong-guess` | 0 |
| `defect` | 3 |
| `unconfirmed` | 3 |

All three candidates are capped at `severity: unconfirmed` because
`commits_behind = 2` on the only repo they span. The cap is a **confidence
floor, not an impact level**: D1 and D2 each make a shipped page unusable, and
the cap says only that the baseline does not support a severity claim while
`integration` is 2 commits behind `main`.

---

## 2. What was driven

The prior two runs drove the Projects page through
`tests/web/fixtures/shell_harness.html`. This run drove the **shipped
`index.html`** at `/`, which is what a user gets, across **nine viewport
widths** (390, 600, 760, 761, 800, 900, 901, 1024, 1280) and all six pages.

That width sweep is the whole reason two of the three defects are new. Every
browser-driving test in the tree and `tools/render_check.py` itself use exactly
two viewports — `{390, 844}` and `{1280, 900}`
(`tests/web/test_shell_live.py:36-37`, `test_projects_page.py:119`,
`test_settings_live.py:129`, `render_check.py:40`). Both defects live strictly
between those two widths, or at 390 on a control no test opens there.

---

## 3. Defects, ranked

### D1 — HIGH. Projects and Settings are unusable at 761–900px

`app.css:2019` — inside `@media (max-width: 900px)`, written for the Flock —
declares `.herd-col { display: none; }` and re-shows columns only through
`.herd[data-level="…"] .col-*`. But `.herd-col` is **also** the class of the
Projects list column (built by `projects.js::scaffold`) and the Settings nav
column (`index.html`). The `.panes2` rescue that re-shows them
(`app.css:1935-1936`, `.panes2[data-level="list"] .herd-col { display: flex }`)
lives inside `@media (max-width: 760px)` and therefore does not apply.

Result: a 140px-wide band, **761px to 900px inclusive**, in which both pages
lose their only means of navigation. Measured, usable (non-zero-box) controls
inside the visible page root:

```
page         390   600   760   761   800   900   901  1024  1280
shepherd       2     2     2     2     2     2     2     2     2
flock         10    10    10    10    10    10    11    11    11
queues         0     0     0     0     0     0     0     0     0
projects       3     3     3     0     0     0     3     3     3
kanban         0     0     0     0     0     0     0     0     0
settings      10    10    10     1     1     1    10    10    10
```

At 800x900 the Projects page renders the single word `DETAIL` over an empty
pane, with two projects in the store and **zero clickable controls** — no
project list, no "New project". Settings renders the Account panel with one
control, `#settings-back`, and clicking it sets `data-level="list"` and changes
nothing on screen, because the list it would reveal is the column that is
hidden.

Screenshots: `runs/band-800-projects.png`, `runs/band-800-settings.png`.

Common real widths inside the band: iPad portrait (768, 810, 820, 834), a
half-screen 1600px desktop, most tablet browsers.

**Sibling sweep.** The set is *every element carrying `.herd-col` in the live
DOM*, enumerated from the browser before comparing (not from the stylesheet — a
column built at runtime by `projects.js` is invisible to a CSS read):

| member | affected | basis |
|---|---|---|
| `#page-flock .herd-col.col-projects` | no | `.herd[data-level="projects"] .col-projects { display: flex }` |
| `#page-flock .herd-col.col-sessions` | no | `.herd[data-level="sessions"] .col-sessions` |
| `#page-flock .herd-col.col-detail` | no | `.herd[data-level="detail"] .col-detail` |
| `#page-projects .herd-col` | **yes** | no rescue in 761–900 |
| `#page-settings .herd-col` | **yes** | no rescue in 761–900 |

2 of 5. A pattern across both `.panes2` pages, not a single site.

### D2 — HIGH. On a phone, the Projects dialogs open invisible and trap the page

`projects.js::scaffold` appends `#dlg-project` and `#dlg-delete` as direct
children of `#page-projects`. `#page-projects` is `.panes2[data-level]`, and
`app.css:1934` — `@media (max-width: 760px) { .panes2[data-level] > * { display: none } }` —
therefore sets `display: none` on both dialogs. An author rule beats the UA
`dialog[open] { display: block }`.

`showModal()` still runs. Measured at 390x844 after tapping "New project":

```
open: true   :modal: true   computed display: none   box: 0x0
#p-save box: 0x0
document.elementFromPoint over the menu button -> HTML   (the modal backdrop)
tap the menu button        : BLOCKED
tap a project row          : BLOCKED
tap New project again      : BLOCKED
visible buttons inside the dialog: []
keyboard Escape            : closes it
```

So: no dialog on screen, no visible backdrop dimming, every tap swallowed, and
the only exit is a keyboard Escape — on the device the spec calls the primary
client, which has no Escape key. A reload is the user's only way out.

Screenshot: `runs/s7-phone390-dlg-project.png` — the page looks untouched; the
focus ring on "New project" is the only sign anything happened.

**Sibling sweep.** The set is *every `showModal()` call site in `web/static/`*:

| member | affected | basis |
|---|---|---|
| `projects.js:551` → `#dlg-project` | **yes** | child of `#page-projects` (`.panes2[data-level] > *`) |
| `projects.js:894` → `#dlg-delete` | **yes** | same parent |
| `flock.js:284` → `#dlg-legend` | no | declared in `index.html` at shell level, outside every page root; measured `display: block`, 390x726 at 390px |

2 of 3. `index.html:388` already records *why* the Projects dialogs are built
inside the page root — so the two halves of this defect are each deliberate and
only their interaction is wrong.

### D3 — MEDIUM. The Flock legend tooltip is left on screen and swallows the next click

`flock.js:301-303` binds `focus` → `showTip` and `click` → `openLegendSheet` on
every `.legend-key`. `<dialog>.close()` restores focus to the element that
opened it, so closing the bucket sheet re-fires `focus` and the tooltip
reappears. `.tip` (`app.css:833`) is `position: fixed; z-index: 40` with
`pointer-events: auto`.

Measured after: hover a legend key → click it (sheet opens) → Escape.

```
desktop 1280x900   tip box t96 b226 l350 r654
   covers  .project   'payments-api 7'   -> elementFromPoint returns the tip
   covers  .card      (first session)    -> elementFromPoint returns the tip
   CONTROLS ACTUALLY BLOCKED: 2

phone 390x844      tip box t94 b224 l74 r378
   covers  .legend-key.bucket-blocked        -> blocked
   covers  .legend-key.bucket-finished       -> blocked
   covers  .legend-key.bucket-unclassified   -> blocked
   covers  .legend-info  'what these mean'   -> blocked
   CONTROLS ACTUALLY BLOCKED: 4
```

On a phone a tap focuses the button, so the tooltip appears on tap, there is no
"move the pointer away" to dismiss it, and it covers the ⓘ control that U1 makes
the documented way into the explainer. Not a dead end — a tap elsewhere blurs
the key and removes the tip — but the tap that lands on the tip is silently
discarded.

Screenshots: `runs/s13b-desktop-tip.png`, `runs/s13b-phone-tip.png`.

**Sibling sweep.** The set is *every absolutely/fixed-positioned overlay this UI
creates outside a `<dialog>`*: `.tip` is the only member — `grep -n
"position: fixed\|position: absolute" app.css` outside `dialog`/`::backdrop`
yields `.tip` alone as a JS-created hover layer. Single site.

---

## 4. Closed items — re-verified, not re-derived

| item | result | evidence |
|---|---|---|
| run-2 defect 1: `kill_failures` has a reader at `#dlg-delete-live` | **closed** | refusal renders `Not stopped, and why: \| <ulid> \| RunnerRefusal: tmux exited 1 … /tmp/tmux-0/shepherd-runner`; project kept; `anomaly.stop_failed` = 1 |
| run-2 defect 1: …and at `#dlg-delete-outcome` | **closed** | reached on a *real landing* (kill raises but the session ends on its own): outcome block reads `1 session record destroyed. \| Not stopped, and why: \| <ulid> \| …`; project gone |
| run-2 defect 2: double-click Create | **closed** | two synchronous `el.click()` calls → **1** POST to `/api/projects`, **1** store row, **1** page row |

---

## 5. The highest-ranked gap from run 2 — closed

**A kill that LANDS**, driven end to end through the browser against an injected
in-process kill that writes `ended_at` through `apply_stop_verdict` (the way
production lands one). No tmux command issued, nothing signalled.

```
dialog before any POST : "This deletes the project and 2 session records,
                          including 1 session still running — the delete will
                          refuse until you choose what happens to them."
store still has project: True          (nothing written before the button)

wire  POST /api/projects/<id>/delete  body={}                          <- default-refuse
      POST /api/projects/<id>/delete  body={"on_running":"kill_sessions"}

page  #dlg-delete-body    "The project is gone."
      #dlg-delete-outcome "2 session records destroyed. | Stopped by this
                           delete: | 01M34V5CP39MXAQ8Q4CY5QS1GE"
      #page-projects data-level -> "list";  list settles to ['Unassigned']

store project gone : True
      kill called  : ['01M34V5CP39MXAQ8Q4CY5QS1GE']
      both session rows: None (destroyed)
console errors: []
```

`DeleteOutcome.killed` is populated on a real landing for the first time, and
the three choices (`kill_sessions`, `orphan`, `cancel`) are all enabled with the
`killable`-derived note *"Ends the running work, then deletes the project."*

---

## 6. Carried-forward item 1 — `app_state["kill.<id>"]`: measured, hypothesis disproved

Driven through the real `orchestration.lifecycle.record_and_terminate` via the
real `tools_m3.kill`, with `ScriptedRunner` as the injected runner.

| question | answer | evidence |
|---|---|---|
| do repeated refusals of the **same** session accumulate? | **No** | 5 `RunnerRefusal`s on one session → **1** row. `set_app_state` upserts on `kill.<session_id>` |
| do they accumulate **per session**? | **Yes** | 4 sessions refused once each → 4 more rows (5 total) |
| does a kill that **lands** clear the row? | **No** | `lifecycle.py:136` calls `set_app_state(key, None)`, and `writes.py:202` is `INSERT … ON CONFLICT DO UPDATE` over `json.dumps(None)`. The row survives holding the string `null` |
| is anything reaped when the session row is destroyed? | **No** | project delete destroyed 6 session rows; all 6 `kill.*` rows survived, keyed by ids with no session |
| does anything **read** the namespace? | **No** | `grep -rn KILL_RECORD_PREFIX src/` → 4 hits, all in `lifecycle.py`, all writes. `grep -rn "DELETE FROM app_state" src/` → exit 1 |

So: the brief's hypothesis ("accumulate unboundedly across repeated refusals")
is **false** — the bound is one row per session ever killed, not per attempt.
What *is* true is a monotonic leak with no reader and no reaper, plus a
docstring that is wrong: `lifecycle.py:66-68` says the record is *"cleared once
the kill is accounted for"* and it is not cleared, it is overwritten with
`null`. Functionally invisible (`get_app_state` returns `None` for both absent
and `null`), so the cost is rows, not behaviour.

**Not filed as a defect.** Severity would be LOW, it matches the disposition
run 2 already recorded ("a store that only grows is a backlog item"), and it has
no user-visible consequence. Filed as a backlog observation below.

**Sibling sweep.** The set is *every `set_app_state` key shape in `src/`*,
enumerated from the call sites:

| namespace | unbounded? | affected | basis |
|---|---|---|---|
| `discovery_status` | no | no | one fixed key |
| `master.*` session / model / last-turn | no | no | fixed keys |
| `autonomy_level` | no | no | fixed key |
| `anomaly.<kind>` | no | no | bounded by `AnomalyKind`; **has** an enumerator, `reads.list_anomaly_counts` |
| `ask_fork.<ask_id>` | yes | **by design** | `core/anomalies.py:88` states it is *"named … and **never deleted**"*, deliberately, because it names a residue file a human must decide about |
| `kill.<session_id>` | yes | **yes** | no reader, no reaper, and its own docstring claims it is cleared |

1 affected of 6. `ask_fork.` grows the same way and is the recorded intent, so
this is a single site rather than a pattern.

---

## 7. Carried-forward item 2 — the reachability probe, rebuilt and proven

Run 2's probe read `document.documentElement.scroll*` only. This one walks every
clipping ancestor, distinguishes a box that *can* scroll from one that cannot,
and counts what it examined so a probe that measured nothing cannot read as a
clean zero.

It was proven in both directions before being trusted, against three controls
planted into the live DOM from the driver (`page.evaluate`; no file written, no
product code touched, nothing leaves the tab):

```
examined: 10   scrollersSeen: 1   unreachable: {"qa3-unreachable": "DIV. [clipX]"}

PASS (a) a plain button in flow                -> reachable
PASS (b) absolutely positioned at left:-4000px
         inside overflow:hidden                -> UNREACHABLE
PASS (c) below the fold of an overflow-y:auto
         scroller (RUN 2's FALSE POSITIVE)     -> reachable
PASS (b) cross-check: playwright refused to click it
PASS (c) cross-check: playwright clicked it
```

Readings with the proven probe: **0 unreachable controls** on all six pages at
1280x900 and at 390x844, once the closed off-canvas drawer is excluded by name
(7 controls per page, counted and reported separately, not silently dropped).
`examined` ranged 7–27 per page, so the zeros are zeros over a non-empty set.

---

## 8. Carried-forward item 3 — the four unguarded POST handlers, re-measured on the wire

Each double-clicked with two synchronous `el.click()` calls, POSTs counted from
the browser's own request stream, durable state read from the store afterwards.

| handler | POSTs issued | durable result | verdict |
|---|---|---|---|
| `projects.js addDraftPath` | 2 × `/repos/add` | `list_repos` = 1 path, 1 row rendered | idempotent |
| `projects.js removeDraftPath` | 2 × `/repos/remove` | `list_repos` = [], 0 rows | idempotent |
| `settings.js choose` | 2 × `/autonomy` `{"level":3}` | `app_state.autonomy_level` = 3, one option pressed | idempotent |
| `chat.js submit` | **1** × `/master/send` | driver received the text once, one bubble | guarded by the emptied input, on the wire |

The recorded decision holds: no durable wrong row, no duplicated side effect.
One thing the decision named as its future cost was **not** re-checked and is
listed as unproven below: whether the chokepoint audit sink appends a row per
autonomy call in production (it would, by design, and two truthful rows for two
real calls is not a wrong row — but that is reasoning, not a measurement).

---

## 9. Carried-forward item 4 — pixels

A 240-character `RunnerRefusal` carrying an unbroken tmux argv was rendered into
`.dlg-reason` and measured at 1280x900:

```
whiteSpace: pre-wrap     overflowWrap: anywhere     textOverflow: clip
font: ui-monospace, "SF Mono", …
reason scrollWidth 422 == clientWidth 422      (no horizontal overflow)
panel scrollHeight 760 == clientHeight 760     (nothing clipped)
document horizontal overflow: 0
dialog 480x762 inside a 900px viewport; .dlg-acts bottom 812 -> on screen
```

The long reason wraps, is not ellipsised, and pushes nothing off screen.
`.dlg-reason` is proven as pixels, not only as DOM text. **At 390px this could
not be measured at all — see D2**, which is why the phone half of this item is
listed as blocked rather than passed.

---

## 10. Fresh ground

| area | result |
|---|---|
| shell, six pages, empty store, 1280 + 390 | 0 console errors, 0 warnings, 0 failed requests, 0 horizontal overflow, exactly one page root visible per page |
| Flock three panes, seven buckets seeded realistically | correct order and `bucket-*` classes: `needs_you, error, unfinished, running, paused, blocked, finished`; stop summary renders all three numbers; drill-down projects → sessions → detail works at both widths; back chevron visible only ≤900px as designed |
| Flock info sheet (U1) | opens from the ⓘ **and** from every legend key, 8 rows, closes on Escape — see D3 for the tooltip it leaves behind |
| SSE | one `/api/events` connection, status slot reads `live`; publishing one event re-read the fleet and the projects column went 1 → 2 with no polling |
| cross-page state | Flock `data-level` survives leaving and returning (`detail` → projects → flock → `detail`), session pane still filled |
| chat | send reaches the driver, `#shepherd-status` shows the turn id; empty submit issues **0** POSTs; an injected 500 renders `request failed (cid-QA3)` in the status slot |
| daemon gone (every `/api/**` aborted) | banner *"The request did not reach the server — Shepherd may not be running."*, stream status `reconnecting`, all three data pages degrade without a single unhandled console error |
| Settings | 10 controls at 1280, all sections reachable, autonomy write lands in `app_state` — **except in the 761–900 band, see D1** |
| Queues / Kanban | declared placeholders, 0 controls at every width, as designed |

---

## 11. Probes of mine that were wrong

Reported as results, because both prior runs produced false readings of exactly
this shape and counting the probe's own actions is what catches it.

1. **Nav clicks at phone width failed** — I had not opened the off-canvas
   drawer. The pane sits at `x: -244..0` by design (`app.css:1996`). Fixed by
   opening `#drawer-open` first; the closed drawer's 7 controls are now excluded
   **by name and counted**, never silently.
2. **Off-by-one on the drawer breakpoint** — my helper used `width < 760` while
   the media query is `max-width: 760px`, inclusive. Every reading at exactly
   760px was wrong until fixed.
3. **"The list still shows the deleted project"** — I read the DOM in the frame
   between `#dlg-delete-outcome` appearing and `renderDeleteOutcome`'s
   `await loadList()` resolving. After a settle the list is `['Unassigned']`.
   **Not a defect; my race.**
4. **"Every Flock card renders `bucket-unclassified`"** — my seed called
   `apply_stop_verdict` only, which writes the eight stop columns but **not**
   `session.state`. `ordering.bucket_of` requires `state is STOPPED` before it
   reads `outcome`, so the rows were case 4 of that function — which is
   documented and correct. Re-seeded through `apply_fold_delta(state=STOPPED)`
   as well and all seven buckets appeared. **Not a defect; my seed.** Worth
   noting that `tests/web/test_projects_page.py::ended_session` has the same
   shape, harmless there but not usable for any Flock bucket assertion.
5. **"The legend keys do not filter"** — they were never filters.
   `flock.js:303` binds every key to `openLegendSheet`, which is U1.
   **Not a defect; my assumption.**
6. **"The tooltip blocks the ⓘ button" (first attempt)** — my own preceding
   click had re-opened the sheet, and the sheet was the interceptor. Re-measured
   with no self-inflicted state; D3 as filed rests on the clean measurement,
   which found a *different* and smaller set of blocked controls than the dirty
   one suggested.

---

## 12. Coverage gaps — what this run did NOT prove

- **Anything above 1280px or below 390px.** The sweep stopped at the two widths
  the tree already uses as bounds.
- **Any real tmux pane.** Every kill in this run was injected in-process. That
  the *shipped* `kill_for_delete` → `kill_session_now` → `record_and_terminate`
  chain lands against a real pane is untested here and forbidden to me.
- **The terminal WebSocket** (`/api/sessions/{id}/terminal`, `terminal.js`,
  `vendor/xterm.js`). Never opened. D67 relocated the session view into the
  Flock's third pane; I drove the pane's header, state, why and actions, not the
  live pty.
- **The production audit sink.** My chokepoint collects `AuditRecord`s into a
  list; I did not measure what `build_audit_sink` writes to disk per call, so
  the "two autonomy POSTs append two audit rows" question in §8 is reasoned, not
  measured.
- **`.dlg-reason` pixels at 390px** — blocked by D2.
- **Real concurrency.** Double-clicks were two synchronous `click()` calls from
  one thread; no two-tab, two-writer, or SSE-during-mutation race was driven.
- **Touch events.** D3's phone half was measured with synthesized mouse events
  that focus the button, which is what a tap does — but no `touchstart` path was
  exercised.
- **`prefers-reduced-motion`, forced colors, zoom, and RTL.** Not touched.

---

## 13. Teardown

- Servers: every `Env` closed in a `finally`; `ss -ltnp | grep 127.0.0.1` → no
  listeners.
- Browsers: `ps` for `chrome|chromium` → none.
- Temp stores: `/tmp/qa3-*` → 0 directories.
- Repo: `git diff --stat -- src/ tests/ tools/` → empty. The only modified
  tracked files are the four `.cc10x/` bookkeeping files and
  `docs/methodology/sdlc-principles.md`, all of which were already modified
  before this run began.
- `docs/probes/` unread except for one capture read as bytes by the fixture
  (`03-after-stop.ansi`); nothing under it written.
- No tmux command was issued. No `~/.claude/` path was read or written.
