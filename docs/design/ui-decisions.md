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

**`core.stops.PALETTE` still carries the old labels**, so the UI copy and the
palette label now differ by intent. Whoever implements this decides whether the
UI reads `PALETTE` and overrides, or carries its own label table — but the hexes
and glyphs must keep coming from `PALETTE`, because the palette test is what
stops them drifting.

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

## Working notes for whoever implements this

- The prototype's JavaScript is a faithful transcription of `fleet.js`,
  `rail.js` and `chat.js` render logic. Porting is mostly moving CSS and
  markup, not re-deriving behaviour.
- Everything in the prototype is `textContent`. §13's no-HTML-sink rule holds
  in the design as written; do not introduce a sink while porting.
- The prototype is a single file with an inline `<script>`. A stray `}` or a
  block of CSS pasted into the script kills the **entire** script silently, and
  the page still renders because the markup is static. Parse the script before
  publishing — `esprima` (pip-installable) caught in one shot what four rounds
  of reading missed.

## Related

- **D57–D64** in `docs/specs/orchestrator-platform.md` — the Projects and work
  source decisions this design draws.
- **§12** — the page-by-page UI spec this revises.
- `docs/backlog/2026-09-21-projects-work-sources-and-ui.md` — the forward-work
  register for all of it.
