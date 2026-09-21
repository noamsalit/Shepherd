# Recon for the projects backend + UI redesign — 2026-09-21

Read-only reconnaissance taken on `integration` @ `4761c1d`, before any plan was
written. Every claim here carries a `file:line`. **Where this contradicts the
backlog, this file is the measurement and the backlog is the memory.**

---

## A. Migration runner — the constraints migration 004 must obey

`src/shepherd/store/migrate.py`.

| Fact | Where | Why it matters to 004 |
|---|---|---|
| `EXPECTED_SCHEMA_VERSION = 3` | `migrate.py:27` | 004 bumps this to 4. |
| Discovery is `sorted(migrations_dir.glob("*.sql"))` — **lexical, not numeric** | `migrate.py:55` | Fine at four files; `010_` would sort before `002_`. Keep the `00N_` shape. |
| Statement splitter is a naive `--`-strip + `;`-split | `migrate.py:76-83` | **No triggers, and no semicolon inside a string literal.** A delete cascade cannot be a trigger. |
| All pending migrations run in **one** transaction; any error rolls back | `migrate.py:165-181` | 004 is all-or-nothing. |
| sha256 of each file is recorded; an edited applied migration refuses start | `migrate.py:66`, `:141-153` | 001–003 are immutable. 004 is append-only. |
| `journal_mode=WAL`, `foreign_keys=ON` during migrate | `migrate.py:88-89` | FK violations inside 004 abort it. |
| Only `controld` calls `migrate()`; `sessiond` never does | `migrate.py:9-11` | No second migrator to coordinate. |

## B. Schema as it actually stands

`workspace` — `001_m1_foundation.sql:30-37`. Columns: `id, owner_id, name,
root_path, created_at, last_activity_at`. **No UNIQUE on `name`** — yet
`upsert_workspace` matches on name. That mismatch is the D57 defect.

`repo` — `001_m1_foundation.sql:39-49` plus `CREATE UNIQUE INDEX ux_repo_path ON
repo(root_path)` at `:136`. **`git_common_dir` has no index and no unique
constraint**, though D48 makes it the binding key — `find_repo_by_common_dir` is
a full scan (`reads.py:74-76`). Worth fixing in 004 while the table is open.

`session` — live definition is migration 002's rebuild, `002:39-118`.
**`session.workspace_id` is `NOT NULL`** (`002:43`).

> **This is the single hardest constraint in W1.** D59's `Unassigned` and D61's
> "orphan them" both require a session to point at *something*, so the reserved
> project must be **seeded inside migration 004 itself**, before any row can be
> moved to it. It cannot be created lazily by a verb at first use.

**Not one foreign key carries `ON DELETE` or `ON UPDATE`** — `repo.workspace_id`
(`001:34`), `session.workspace_id` (`002:43`), `session.repo_id` (`002:44`),
`session.parent_session_id`, `session.retry_of`, `mailbox_message.session_id`
(`003:37`). SQLite's default is `NO ACTION`.

So **D61 has no substrate today.** A `DELETE FROM workspace` through the writer
connection (which sets `foreign_keys=ON`, `db.py:102`) raises `FOREIGN KEY
constraint failed` whenever any repo or session points at it. 004 must either
rebuild `session` to add `ON DELETE CASCADE` — as 002 already did once, since
SQLite cannot `ALTER` an FK — or the cascade lives in the verb. **Decide this
explicitly; do not let it be discovered during implementation.**

`PRAGMA defer_foreign_keys=ON` is the idiom 002 used inside the runner's
already-open transaction (`002:31-37`) — `foreign_keys=off` is a no-op there.
004 must copy that, not re-derive it.

## C. The defect D57 names, measured

`upsert_workspace(connection, name, root_path)` — `writes.py:104-118`:

```python
row = connection.execute("SELECT * FROM workspace WHERE name = ?", (name,)).fetchone()
```

Identity is the **name**. And the name is generated from the path basename:
`_workspace_name(path)` is `Path(path).name or "local"` (`binding.py:203-205`).

So `/work/api` and `/personal/api` both become the project `"api"`, and the
second silently overwrites the first's `root_path`. **That is the collision
engine, and both halves have to go together** — matching on name, and deriving
the name from a basename.

Three further sharp edges in the same neighbourhood:

1. `root_path=None` means *untouched*, never *cleared* — pinned by
   `tests/store/test_store_delegation.py:487-506`.
2. `upsert_repo`'s **update arm never touches `workspace_id`**
   (`writes.py:137-141`), so a repo can never move between projects by this
   verb, and it unconditionally re-activates. That is the one-repo-one-project
   assumption D60's join table has to break.
3. **`workspace.last_activity_at` is never written by anything in `src/`.** It
   is always NULL — and it is projected to the UI and the master anyway, via
   `project_workspace()` at `toolsurface/tools_m1.py:150-159`. A column the page
   renders and nothing fills. Not in the backlog; found here.

## D. `admission.py` — what "the workspace-root branch" is

`_registered_roots(store, workspace_id)` — `admission.py:112-151`. The branch W1
step 2 deletes is the comprehension at `:129-133` that prepends
`workspace.root_path` to the repo paths. It is a full `list_workspaces()` scan
filtered in Python **because no `get_workspace(id)` verb exists** — add one.

**The T11-1 special case**, quoted in-source at `admission.py:118-121`: before
T11-1 the allowlist was the workspace root *alone*, which refused a spawn into
any repo not nested under it — the normal case — and refused everything for a
workspace whose root was NULL. The fix made the repo paths the population and
kept the root as an *additional* permitted root.

**Its mirror half is at `:141-143` and must survive the change:** a stored root
that will not canonicalize is **named and refused**, never silently dropped,
because a silent drop narrows the allowlist and then lies about it. Keep that
property when the population changes.

Matching is over **path components**, never strings (`:184`), innermost wins
(D22, `:188`), and an empty allowlist is a refusal, not permission — *"no
registered root and no registered repo … is not an allowlist of everything"*
(`:170-175`). All three survive W1 unchanged.

## E. Discovery — four call sites, three auto-creates

`bind_cwd_to_repo(store, cwd)` — `binding.py:213-265`, *"never raises"*. Called
from exactly four places:

- `discovery_loop.py:418` — the scan lane, on `session is None`
- `hook_lane.py:165` — the hook lane, D47's *"first event of any kind"*
- `hook_lane.py:179` — `_rebind`, a session that moved
- `hook_lane.py:203` — `_with_foreign_repos` (blocker T11-3), for `repos_touched`

Four branches inside it; **three write a workspace**: not-a-repo (`:223`), bare
repo (`:232`), new repo (`:251`). The steady-state path — a known common dir
(`:240-247`) — writes nothing. D59's policy belongs at this chokepoint, which is
what makes it one decision rather than one per lane.

`RepoBinding.workspace_id` is **non-optional** (`binding.py:63-68`), which is
precisely why every branch has to produce a project and why `Unassigned` is the
honest answer instead of an auto-created one.

**`discover_repos()` has no caller in `src/`** (`discovery.py:28-66`) — only
`tests/signals/test_discovery.py`. It is the sole documented justification for
`workspace.root_path` existing (`discovery.py:1`), and nothing wires it.
Removing `root_path` makes that module docstring false. Decide the module's fate
in the plan rather than leaving a lie behind.

## F. Secondary hazard for delete and orphan

`Store.fleet()` (`reads.py:~205-215`) is an **INNER** `JOIN workspace`. A session
whose workspace row vanished disappears from the Flock page with no trace. That
makes "orphan into Unassigned" a correctness requirement, not a courtesy.

## G. The shipped frontend — 14 files, 10 hand-written

`src/shepherd/web/static/`, served by `server.py:47` (`STATIC_PREFIX`), no build
step (D51). `index.html` 173 lines, `app.css` 582, `app.js` 140, `fleet.js` 421,
`chat.js` 342, `rail.js` 82, `session.js` 219, `terminal.js` 176, `sse.js` 38,
`escape.js` 21 (**dead — nothing imports it**), plus `vendor/` (xterm 6.0.0 ESM,
its CSS, LICENSE, VERSION.txt).

**U18 confirmed, and worse than recorded.** There is no `[hidden]` rule anywhere
in `app.css` — the only `display:none` in the tree is inside vendored xterm CSS.
The page relies on the UA default. And `.chat-view` is already `display: grid`
(`app.css:483-488`), so **the latent bug U18 predicts is already present in the
shipped page**, not merely a risk the redesign introduces. The redesign must land
`[hidden] { display: none !important }` explicitly.

**Theming:** no dark mode, no `prefers-color-scheme`, no breakpoints, no token
layer. The only custom properties are `--gap` and the eight `--bucket-colour`
values (`app.css:151-184`), and colour is applied to **text only** — never as a
background or wash. U16's wash is therefore new CSS, not a tweak.

The page is a split personality today: fleet/chat chrome is scheme-agnostic
(effectively unstyled-light), while the session page and terminal are hard-coded
dark (`app.css:359-462`). A dark-only redesign is largely promoting the session
palette to the whole document.

**SSE:** one `EventSource("/api/events")` (`sse.js:16`), one unnamed `message`
listener by design, browser-native reconnect with `Last-Event-ID` against the
server ring's `seq`. Every envelope triggers a **full fleet + tree re-read and
full re-render** (`app.js:119-130`). Worth knowing before adding pages.

**The audit tail** is `chat.js:242-260` into `#chat-audit`, an explicit
four-field whitelist (`at, tool, decision, approved_by`) with `args` deliberately
excluded per D25. U6 moves it to Settings → Data; keep the whitelist.

**Routes the UI never calls today:** `/api/projects`, `/api/mailbox`,
`/api/sessions/{id}/send|ask|interrupt|kill|permission`, and POST `/api/sessions`.
The Projects page and the U17 decision card draw on these.

## H. The tests that gate this work

Under `tests/web/`: `test_palette.py` (parses **both** the JS label/glyph tables
**and** the CSS hexes back out of the shipped files), `test_frontend_escaping.py`,
`test_the_chat_page_has_no_html_sink`, `test_rail.py`, `test_session_wiring.py`
(walks the module graph from `index.html`), `test_session_page.py::test_pty_bytes_never_reach_innerHTML`,
`test_the_page_does_not_re_derive_the_order`, `test_frontend_no_build_step.py`.

Plus `tests/orchestration/test_admission.py` (the file *about* `root_path`),
`tests/store/test_verbs.py`, `test_store_delegation.py`, `tests/golden/corpus.py`
(the `Binding` dataclass carries `root_path`), and ~60 fixture call sites passing
`root_path` positionally to `upsert_workspace`.


---

## I. The byte-freeze, worked out exactly — read this before touching `web/`

This is the hardest constraint in the tree, and the backlog's one-line summary
("spend one `post_milestone` declaration") is not enough to implement against.

`tests/boundaries/consumer_manifest.json` carries four relevant blocks:
`baseline` (the step-0b freeze, **never rewritten**), `files` (the current
comparison set), `rebase` (T24's single permitted re-base), and `post_milestone`.

Two tests enforce it, in `tests/boundaries/test_consumer_surface_frozen.py`:

**1. `test_completing_l4_changed_no_consumer_byte` (`:73-82`)** — `files` must
equal the live tree exactly: no added, no removed, no changed. So every edit
means updating that path's sha256 in `files`. Mechanical.

**2. `test_a_rebase_declares_every_path_whose_digest_moved` (`:115`)** — the one
with teeth:

```python
later = boundary.post_milestone_paths(manifest)
assert boundary.moved_paths(baseline, files) == frozenset(declared) | later
assert later.isdisjoint(frozenset(declared))
```

`moved_paths` (`_imports.py:229-240`) compares `baseline` against `files` and
uses `was.get(path) != now.get(path)`, so **a path absent on either side counts
as moved**. That means a *new* file and a *deleted* file are both "moved" and
both must be declared.

So the rule, stated operationally:

> **Every path whose bytes differ from the step-0b baseline — including files
> created and files deleted — must appear in exactly one of
> `rebase.regenerated_paths` or `post_milestone.edits`, and never both.**

`rebase.regenerated_paths` is already spent on five paths:
`web/routes.py`, `web/static/app.css`, `web/static/app.js`,
`web/static/chat.js`, `web/static/index.html`.

**Consequence, and it is good news:** those five are already accounted for.
Editing them again needs only their `files` hash updated — they stay in
`moved_paths`, they stay declared, and the disjointness assertion still holds.
**They must NOT be added to `post_milestone`**, which is the trap.

Everything else under `web/` and `cli/` that moves needs a `post_milestone.edits`
entry: `{path, at, by, why}`, all four non-empty strings, validated by
`post_milestone_paths` (`_imports.py:242-266`).

**`post_milestone` entries are per PATH, not per EDIT** — `assert len(seen) ==
len(set(seen))` forbids a path appearing twice. `web/static/rail.js` **already
has an entry** (the 2026-09-20 publish scrub, whose `why` ends *"Comment text
only: no statement, no selector and no behaviour changed."*). If the redesign
touches or deletes `rail.js`, that entry must be **rewritten to describe the
path's whole divergence from baseline**, not appended to — and the old sentence
stops being true, so leaving it would be a false record in a gate whose entire
purpose is an honest one.

### Three more gates in the same area

- **`web/server.py` must stay byte-identical** —
  `test_consumer_surface_additive.py:280` `test_web_server_is_byte_unchanged`.
  It is not merely frozen, it is pinned.
  **This forbids serving any new file type.** `_CONTENT_TYPES` (`server.py:49-53`)
  allows exactly `.html`, `.js`, `.css`; anything else 404s. No fonts, no SVG
  files, no JSON data files, no images. Inline SVG in markup is fine.
- **`test_the_pre_m4_route_mappings_are_unchanged`** (`:170`) — a subset check
  against `pre_m4_routes.json`. **Adding** routes is allowed; re-pointing an
  existing one is not.
- **`tests/web/test_routes.py:89-114`** holds a **closed-set literal of every GET
  path**, widened by hand. And `tests/web/test_routes_m3.py:112` asserts an
  arrival count: `checked == len(routes.POST_ROUTES) - 1 == 9`. **Adding POST
  routes breaks that literal `9`** — it is a number typed into a test, and five
  new verbs will move it.

### Registering a verb — the checklist that survives the gates

1. New `toolsurface/tools_<x>.py` exposing `build_*_tools()` / `register_*_tools()`.
   `ToolDef` has **six fields and no defaults** (`types.py:180-191`); the schema
   must be `{"type": "object", "properties": {...}}` or `register()` raises
   `SchemaInvalid`.
2. Wire into `toolsurface/compose.py` **before** `install_chokepoint` (`:457`)
   and `freeze_registry()` (`:473`).
3. Anything above `local_read` is unreachable in a process with no chokepoint
   (`registry.py:144` `GATE_FREE_CLASSES`) — that is the `cli/` fallback root.
4. Routes into `API_ROUTES`/`POST_ROUTES` **and** `QUERY_ARGS`/`BODY_ARGS`;
   every declared field must be a real property of the tool's schema.
5. Widen the GET closed-set literal and fix the POST arrival count.

### One more thing the prototype gets wrong for this environment

The prototype's `<head>` pulls **Instrument Sans and JetBrains Mono from Google
Fonts**. This app binds loopback only (`server.py:41`, `BindAddressRefused` for
anything else) and is meant to work on a machine that may be offline. A remote
font is a third-party request from a local tool, a render stall when the network
is slow, and a new file type the server cannot host locally anyway (see the
`_CONTENT_TYPES` pin above).

**Decision: drop the webfont; use a system font stack.** The design's type
choices survive as fallbacks. Recorded here because it is a deviation from the
published prototype and should not be silently absorbed.


### Proven, not asserted — the gate simulated against the planned edits

The rules above were run against the real manifest through the real helpers
(`tests/boundaries/_imports.py`) before any builder relied on them. Five
predictions, five confirmations:

| Simulated edit | Gate |
|---|---|
| edit `app.css` (already in `regenerated_paths`), no new declaration | **passes** |
| add `projects.js`, undeclared | **fails** — `undeclared=['web/static/projects.js']` |
| add `projects.js`, declared in `post_milestone` | **passes** |
| delete `escape.js`, undeclared | **fails** |
| declare `app.css` in `post_milestone` as well | **fails** — `dup=['web/static/app.css']` |

### And one trap neither the backlog nor §I predicted

**`web/static/chat.js` cannot be deleted or renamed. It can only be edited.**

It is the only static file that was **created after** the step-0b baseline, and
T24's rebase claimed it. So:

- `baseline` does not contain it; `files` does → it is currently "moved", and
  `regenerated_paths` declares it. Consistent.
- Delete it, and it becomes absent from *both* blocks. `moved_paths` uses
  `was.get(path) != now.get(path)`, so absent-on-both is **not moved** — while
  `regenerated_paths` permanently asserts that it *did* move.
- The equality `moved == declared | later` then fails with
  `declared-but-not-moved = ['web/static/chat.js']`, and it **cannot be
  repaired**: adding it to `post_milestone` trips the disjointness assertion,
  and `rebase` may not be rewritten (`assert rebase["regenerated_by"] in (None,
  "T24")`).

Measured for every static file:

| File | In baseline | In rebase | Deletable / renamable |
|---|---|---|---|
| `app.css`, `app.js`, `index.html` | yes | yes | yes |
| `escape.js`, `fleet.js`, `rail.js`, `session.js`, `sse.js`, `terminal.js` | yes | no | yes, with one `post_milestone` entry each |
| **`chat.js`** | **no** | **yes** | **no — pinned in place** |

**Consequence for the redesign:** `fleet.js` → `flock.js` is fine (verified:
both declared, gate passes). **`chat.js` → `shepherd.js` is not.** The
conversation module keeps the filename `chat.js`; the *page* is called Shepherd.
A module filename is not a user-facing label, and paying for that rename means
either breaking a freeze gate or rewriting a re-base that is explicitly spent
once.
