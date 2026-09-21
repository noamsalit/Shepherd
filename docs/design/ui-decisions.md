# UI redesign — decisions, 2026-09-21

**Status: design only. No file under `src/shepherd/web/` has been changed.**

The design is a working prototype, published as an artifact:
**https://claude.ai/artifact/1HFNab8sksQdz7WAP4SfFc**

It is a faithful, clickable mock — the real layout, the real palette, canned
data — not a client. It cannot reach a daemon, which is deliberate: design
decisions were taken against pixels, not against a running fleet.

A second artifact records what the UI looked like *before* this work, rebuilt
from the shipped `index.html`, `app.css` and render logic so the two can be
compared: **https://claude.ai/artifact/JMSzca6pWM38GHuFVmNQeE**

**Read this before touching `web/`.** `web/static/` is byte-frozen by
`tests/boundaries/consumer_manifest.json`, so every real edit there costs a
`post_milestone` declaration. That is a reason to implement a settled design
once, not fifteen iterations of one.

---

## The shape

Dark only, by instruction. A collapsible left pane holding six pages:

| Page | What it is |
|---|---|
| **Shepherd** | the orchestrator conversation (was "chat") |
| **Flock** | the sessions (was "fleet"/"herd") |
| **Queues** | placeholder, not discussed |
| **Projects** | project lifecycle and configuration |
| **Kanban** | placeholder, not discussed |
| **Settings** | ten sections under *Yours* and *This instance* |

Palette: near-black with a blue bias (`#08090D` → `#1C212D`), violet `#7A5CF0`
as the accent, blue `#4C7DF0` beside it. Instrument Sans for UI, JetBrains Mono
for tool names and data. **The eight bucket hexes are untouched** — they are
asserted by `tests/web/test_palette.py` against `core.stops.PALETTE`.

## Vocabulary changed — labels only

The `Bucket` values are **unchanged**; only what the UI prints changed. Nothing
in `signals/stop_rules.py`, the store, or the 90-day stop log moves, and old
records stay readable.

| Value in code | Printed as | Why |
|---|---|---|
| — (the page) | **Flock** | sheep come in flocks; herds are cattle. A shepherd tends a flock. |
| `unfinished` | **stranded** | it stopped, it will never resume on its own, only you can restart it. Rejected *strayed*: straying means going the **wrong way**, which is `derailed` — one of eight reasons in this bucket, so it would mislead on the other seven. |
| `paused` | **limit exceeded** | the bucket is exactly two reasons, `rate_limited` and `quota_paused`. "Paused" was vaguer than the thing it names. |
| `unclassified` | **unknown** | plain. |

**The renames belong in `core.stops.PALETTE`, not in a second table.**
`tests/web/test_palette.py` asserts the page's labels equal `PALETTE.label` for
all eight buckets, and it is right to: a UI-side label table is precisely the
drift it exists to catch. Change the label strings at the source. The `Bucket`
*values* do not move, so `stop_rules.py`, the store and the 90-day log are
untouched.

## Settled

- **U5 — "not classified" is "unknown"** in the UI. Bucket value unchanged.
- **U6 — the audit tail is not on the Shepherd page.** It is in Settings → Data.
  Pending approvals stay on Shepherd, inline at the blocked turn, because that
  is where the decision belongs.
- **U7 — a session card carries four things and no more:** bucket glyph and
  colour, title, **the ask verbatim** (only when stopped or waiting), and
  relative time. Progress is a 2px hairline on the card's bottom edge, never a
  text line. Deliberately out: model, ownership, session id, confidence,
  workspace path — all real, none of them changes which card you tap.
- **U8 — relative time is spelled out and scales to years.** `just now`,
  `2 minutes ago`, `11 days ago`, `1 year ago`, and **`never seen`** when there
  is no timestamp at all rather than claiming `just now`.
- **U9 — the Flock is three panes:** projects → session cards → the session,
  and the session is shaped like the Shepherd conversation. On a phone it is a
  drill-down, one level at a time, with a back chevron.
- **U10 — a legend of all eight buckets sits at the top of the Flock**, glyph
  and colour and name, with a tooltip per key. Each tooltip carries an
  **acts:** line taken verbatim from `PALETTE.who_acts`, because that field
  already exists and is the thing that actually distinguishes the buckets.
- **U11 — a `needs you` session shows the engine's own prompt**, numbered the
  way the TUI numbers it, and Shepherd sends the keystroke. **Not** flattened to
  approve/reject: that would throw away *"Yes, and don't ask again for psql
  commands in payments-api"*, which is the option carrying the scope and usually
  the one you want. An **idle** session gets no card — it is not sitting on a
  prompt, so the composer is the whole affordance.
- **U12 — the autonomy levels are not numbered in the UI.** D8's scale starts
  at 2 for historical reasons the spec never justifies, and the numbers mean
  nothing to a reader. The two options read *"Ask me before anything leaves this
  machine"* and *"Approve automatically"*, the second stating that
  auto-approved is never unlogged.
- **U13 — Settings is ten sections under two headings**, *Yours* (Account,
  Notifications, API keys) and *This instance* (Autonomy, Shepherd, Discovery,
  Limits, Users & access, Data, System). Anything unbuilt carries a `not built`
  chip **and says why in the panel**. `shepherd uninstall` is dropped from the
  UI entirely.
- **U16 — the card takes a wash of its bucket colour, and the legend is the
  glyph plus coloured text.** Chosen on 2026-09-21 by building six treatments
  and comparing them on a real list (`payments-api`, four cards, four buckets),
  not by describing them. Rejected: a coloured frame with coloured text, a
  coloured left stripe, coloured text alone, a named chip, and filled cards with
  filled legend pills. The wash is ~16% of the bucket colour over the card
  ground; the ask stays neutral so the colour carries the state and the words
  carry the content.
- **U14 — the Projects page is two panes**, list and detail, with `Unassigned`
  pinned last and visually distinct. Repo paths are shown in full, and edited in
  the Edit dialog rather than inline. Sessions listed on a project are links
  into the Flock.

## Resolved 2026-09-21, after the first review of the prototype

The owner reviewed U1–U4 and U15 and answered four of the five. **None of them
was a blocker**, and this section says so rather than leaving them looking like
gates.

- **U2 — the Needs-You rail stays out, for now.** It is not coming back to the
  Shepherd page. The intent is that it lives on the **Flock page only**, when it
  returns at all. This reverses the concern recorded below: a rail on every page
  was §12's design, and one page is the owner's.
- **U3 — the autonomy toggle is a Settings control and nothing else.**
  Recorded as **D65**, which revises §12: that section used to place the toggle
  on the master page *"visible at all times"*. The level is still legible from
  behaviour — at the asking level you get cards, at the auto level you do not —
  so what was lost is display, not information.
- **U15 — model and engine per spawned session is deferred**, with no
  precedence rule adopted. Today the only lever is `spawn_session`'s `model`
  argument, and `engine="claude_code"` stays a literal. Revisit when a second
  engine exists or a project genuinely wants a different model from the machine
  default.
- **U4 — logging unclassified stops** was never a UI question; it is W-level
  work tracked in the backlog.

## Open

Nothing is gating the implementation.

- ~~**U1 — the tooltip interaction.**~~ **Resolved: one `ⓘ` opens a sheet
  explaining all eight at once.** Hover and keyboard focus keep the single-key
  popover on a pointer device; a **tap** anywhere in the legend — a key or the
  `ⓘ` — opens the sheet. A key that did nothing on tap would be a dead control,
  and eight explanations read better together than one at a time on a phone.
  On a narrow screen the sheet rises from the bottom edge.
  *The reason originally recorded for going hover-only was wrong: the note said
  tap "fights the card tap", and it does not — the legend is its own strip and
  its keys are nowhere near the session cards. Corrected rather than quietly
  dropped.*
- ~~**U2 — the Needs-You rail has no home in the new design.**~~ Answered
  above: out for now, Flock page only if it returns.
- ~~**U3 — the autonomy toggle has no home outside Settings.**~~ Answered
  above and recorded as D65.
- **U4 — stops that were never classified are not logged.** `logs/stops.py`
  records evidence and verdict for every stop it *sees*, so `unknown` verdicts
  are already durable. The gap is the cohort whose record never arrived —
  currently only a count on a page. Log the absence at the point the fleet
  notices a stopped session with no record.
- ~~**U15 — model and engine per spawned session.**~~ **Deferred**, no
  precedence rule adopted. `spawn_session`'s `model` argument is the only lever
  and `engine="claude_code"` stays a literal in `orchestration/spawn.py`.

## U17 — the decision card needs a projection that does not exist yet

**Decided 2026-09-21: build it.** U11 says a `needs you` session shows the
engine's own prompt with its numbered choices, verbatim. Nothing projects that
today:

* `SidecarState` reports three values — `WAITING`, `NOT_WAITING`, `ABSENT`. A
  state, not a prompt.
* `answer_permission` sends keystrokes and returns `DialogAnswer(decision,
  reason, keys_sent)`. It answers a dialog; it never describes one.

So the prompt text and its options have to be **read off the pane** and turned
into `{text, choices[]}`. `docs/probes/2026-09-14-schemas/tmux-tui/` has the
captures to build it against, and §12's own mockups are drawn from them.

Three things that will bite, all already known to the tree:

1. **Attached sessions have no pty of ours.** The card must render read-only for
   them and say so, rather than showing three buttons that go nowhere.
2. **The choices are the engine's, and they move with its version.** A parser
   pinned to one wording breaks on an update. Whatever it cannot parse degrades
   to the ask plus approve/reject, never to a guess — the same rule `unknown`
   follows everywhere else.
3. **C15's trust dialog** leaves a session neither `starting` nor `needs_you`,
   and a blind Enter answers *"No, exit"*. Any prompt parser meets it eventually.

## U18 — the pages depend on a reset that `web/static/` does not have

Found on 2026-09-21 the first time the prototype was opened in a real browser:
**every "hidden" page was rendering underneath the visible one.**

Each page sets `display` from a class — `.scroll`, `.herd`, `.panes2` — and an
author class rule beats the browser's own `[hidden] { display: none }`. The
prototype only looked correct because the artifact wrapper injects
`[hidden] { display: none !important }`. `web/static/index.html` has no such
reset, so porting this design without that one line puts every page on screen at
once.

The rule is now in the prototype's own stylesheet, commented, so it travels with
the design instead of being rediscovered.

**And the general point, which is the reusable part:** three bugs reached this
prototype that reading could not catch — CSS pasted into the `<script>`, a click
handler never inserted, a temporal dead zone — plus this one, which no amount of
reading would ever have found because it was a rule the page did not contain.
A page is not verified until a browser has run it. `scratchpad/ui/render_check.py`
is that check: it opens every page at phone and desktop width, fails on any
console error, and asserts nothing scrolls sideways.

## Working notes for whoever implements this

- The prototype's JavaScript is a faithful transcription of `fleet.js`,
  `rail.js` and `chat.js` render logic. Porting is mostly moving CSS and
  markup, not re-deriving behaviour.
- **Correction, 2026-09-21: "everything in the prototype is `textContent`" was
  false.** Counted: the prototype has **eight** `innerHTML` assignments. Seven
  build inline SVG by string concatenation (lines 2520, 2688, 2796, 2837, 2858,
  3101, 3617) and one — `prose.innerHTML = line[1]`, line 2814 — assigns a bare
  variable, which is the sink shape §13 exists to prevent.
  `tests/web/test_frontend_escaping.py` permits a sink only when its right-hand
  side is a **single quoted literal with no concatenation**, so all eight are
  findings and none of them ports as written. The icons become `createElementNS`
  calls or static markup; the prose span becomes `textContent`. Budgeted as
  explicit scope in the plan rather than left to be found mid-port.
- The prototype is a single file with an inline `<script>`. A stray `}` or a
  block of CSS pasted into the script kills the **entire** script silently, and
  the page still renders because the markup is static. Parse the script before
  publishing — `esprima` (pip-installable) caught in one shot what four rounds
  of reading missed.

## What implementing this actually requires

**The Shepherd and Flock pages can be built now.** Every read and write they
need already exists: `/api/master/send`, `/api/approvals`, `/api/audit`,
`/api/autonomy`, `/api/fleet/tree`, `/api/sessions/{id}`, `.../output`,
`.../permission`. No backend work, no migration.

**The Projects page cannot.** It is designed against verbs that do not exist —
`create_project`, `rename_project`, `delete_project`, `add_repo`,
`remove_repo` — and against a `list_repos` that exists in the store with no
tool and no route, so the UI cannot see a project's repos at all. **W1 in the
2026-09-21 backlog is a hard prerequisite.** The work-source section needs M5's
`queue` table on top of that.

**Settings is partial, and honestly so.** Autonomy, Discovery's hook status,
Data's audit tail and System's facts are all real today. Limits are compiled
constants. Everything else is a labelled placeholder.

### Two shipped tests will go red, and both are decisions, not breakages

1. **`tests/web/test_palette.py::test_palette_matches_core_stops`** asserts the
   page's `LABEL` table equals `PALETTE.label` for all eight buckets. Our
   renames — **stranded**, **limit exceeded**, **unknown** — break that.
   **The test is right and this file was wrong.** An earlier paragraph here said
   the implementer could "decide whether the UI reads `PALETTE` or carries its
   own label table". It cannot: a second label table is exactly the drift that
   test exists to prevent. **The rename belongs in `core.stops.PALETTE`.** The
   `Bucket` *values* still do not move, so nothing in `stop_rules.py`, the store
   or the 90-day log is affected.
2. **`tests/web/test_rail.py::test_rail_is_on_every_page`** asserts the rail slot
   sits in `index.html` before `<main>` — that it is the shell and not one view's
   child. U2 takes it off the shell. That test encodes §12's rule, so removing it
   is reversing a decision: it needs a decision row of its own, the way D65
   handled the autonomy toggle. Do not delete the assertion quietly.

### And the freeze

`web/static/` is byte-frozen by `tests/boundaries/consumer_manifest.json`.

**Correction, 2026-09-21: an earlier version of this section said to spend one
`post_milestone` declaration on the whole redesign. That is not possible.**
`post_milestone_paths` (`tests/boundaries/_imports.py:242-266`) asserts
`len(seen) == len(set(seen))` over the entries' `path` fields — entries are per
**path**, not per edit and not per milestone.

The rule, stated so it can be implemented: **every path whose bytes differ from
the step-0b `baseline` — including files created and files deleted — must appear
in exactly one of `rebase.regenerated_paths` or `post_milestone.edits`, and
never both.** The five paths T24 already rebased (`web/routes.py`, `app.css`,
`app.js`, `chat.js`, `index.html`) are therefore edited *without* a new
declaration, and adding one for them **fails** the gate.

`web/static/chat.js` is additionally pinned: it may be edited, never renamed or
deleted. It is the only static file created after the baseline, so deleting it
makes `moved_paths` report it as un-moved while the rebase block still declares
it — an equality with no repair available.

`docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` §I carries the
measured table of which files can move and five gate simulations run against the
real manifest.

## Related

- **D57–D64** in `docs/specs/orchestrator-platform.md` — the Projects and work
  source decisions this design draws.
- **§12** — the page-by-page UI spec this revises.
- `docs/backlog/2026-09-21-projects-work-sources-and-ui.md` — the forward-work
  register for all of it.
