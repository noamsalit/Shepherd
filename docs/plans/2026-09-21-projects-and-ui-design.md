# Design — projects backend + the dark UI redesign

**2026-09-21.** Written through the cc10x exploration route (DESIGN mode, fast
path: goal, constraints and acceptance were all stated rather than inferred).
Foundation: `docs/design/ui-decisions.md` (U1–U18), spec §3 D57–D65, and
`docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` — which is the
measurement this design is built on and outranks memory where they disagree.

---

## Scope triage — two sub-projects, sequenced

This is multi-subsystem. The two halves ship independently:

| # | Sub-project | Independently shippable? |
|---|---|---|
| **1** | **Projects backend** — migration 004, the join table, five lifecycle verbs, `Unassigned`, delete semantics | Yes. Touches no file under `web/static/`. |
| **2** | **The UI redesign** — Shepherd, Flock, Projects, Settings, plus Queues/Kanban placeholders | Depends on (1) for the Projects page only. |

They are sequenced rather than split because the Projects page is sub-project
1's acceptance test: five verbs with no caller are five unproven verbs.

## Purpose

Make a project a **declared** object with a lifecycle instead of one inferred
from a path basename, and give the fleet a UI that a person can drive from a
phone. Today a project is auto-created from `Path(cwd).name`, two directories
called `api` silently become one project, and the page that would show you this
does not exist.

## Users

One person on one machine (the owner), driving from a phone against a loopback
server over a tunnel. Multi-user is explicitly out (see Out of Scope) but
`owner_id` already exists on every row and is not removed.

## Success criteria

1. `/work/api` and `/personal/api` are two projects, proven by a test that fails
   against today's code.
2. A project can be created, renamed, deleted, and have repo paths added and
   removed — by the human through HTTP and by the master through the tool
   surface, using **the same verbs**.
3. A session that matches no declared project lands in `Unassigned` and is
   visible on the Flock page. A binding failure is never a dropped session.
4. Deleting a project with running sessions presents three choices and takes
   none of them silently.
5. Every page renders at 390×844 and 1280×900 with zero console errors and no
   horizontal overflow, proven by `tools/render_check.py` against the **served**
   page, not the prototype.
6. Suite green, `mypy --strict` clean, 105 boundary rules green, at every phase
   boundary.

## Constraints

Carried from the artifact's intent block; the load-bearing ones here:

- **Migration 004 is append-only and runs in one transaction.** 001–003 are
  sha256-pinned and immutable (`migrate.py:141-153`).
- **The runner's statement splitter is naive** (`migrate.py:76-83`): no triggers,
  no semicolon inside a string literal.
- **Migrations are discovered in lexical order** (`migrate.py:55`) — keep `00N_`.
- **`session.workspace_id` is `NOT NULL`**, so `Unassigned` must be seeded in the
  migration, not created lazily at first use.
- **`web/server.py` must stay byte-identical**, which pins `_CONTENT_TYPES` to
  `.html`/`.js`/`.css`. No fonts, images, SVG files or JSON data files may be
  added to the static tree.
- **`web/static/` is byte-frozen.** Every path whose bytes differ from the
  step-0b baseline must appear in exactly one of `rebase.regenerated_paths` or
  `post_milestone.edits`. See recon §I for the worked mechanics.
- No build step, no npm, plain ES modules (D51). No `Any`, `mypy --strict`.
- No `innerHTML`/`outerHTML`/`insertAdjacentHTML` anywhere in the static tree.

## Out of scope

M5 queues and work-item providers beyond a disabled placeholder (W3);
bring-your-own-harness; credentials and multi-user auth; real sandboxing;
Queues and Kanban beyond nav placeholders; model/engine-per-session precedence
(U15, deferred); the matrix view (§12 Page 2b); the LLM verdict lane (D34).

---

## Approach chosen — sub-project 1

### Migration 004, rehearsed rather than reasoned about

The shape below was **executed against the real 001–003 schema with real rows**
before this document was written. Result: applies clean, `PRAGMA
foreign_key_check` empty, both delete paths work.

```sql
ALTER TABLE workspace ADD COLUMN description TEXT;
CREATE TABLE project_repo (
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  repo_id      TEXT NOT NULL REFERENCES repo(id),
  added_at     TEXT NOT NULL,
  PRIMARY KEY (workspace_id, repo_id)
);
INSERT INTO project_repo (workspace_id, repo_id, added_at)
  SELECT workspace_id, id, added_at FROM repo;
ALTER TABLE repo      DROP COLUMN workspace_id;
ALTER TABLE workspace DROP COLUMN root_path;
CREATE INDEX ix_repo_common_dir ON repo(git_common_dir);
INSERT INTO workspace (id, owner_id, name, description, created_at)
  VALUES ('unassigned', 'local', 'Unassigned', '…', '1970-01-01T00:00:00Z');
```

**The finding that shapes the whole migration: `session` is never rebuilt.**

The obvious reading of D61 — "delete cascades to sessions" — suggests
`ON DELETE CASCADE` on `session.workspace_id`. SQLite cannot `ALTER` a foreign
key, so that would mean rebuilding a 40-column table the way migration 002 did.
That is the highest-risk operation available here and it buys nothing:

1. **The DB cannot express D61 anyway.** The verb must offer *kill / orphan /
   cancel* before anything is deleted, so the verb runs regardless.
2. **A schema-level cascade is a loaded gun.** It makes any future accidental
   `DELETE FROM workspace` destroy session rows silently — the opposite of the
   rule this project applies everywhere else.
3. `DROP COLUMN` was assumed to fail on `repo.workspace_id` because it is the
   referencing side of a foreign key. **That assumption was wrong** — probed
   against SQLite 3.45.1, it succeeds. So no rebuild is needed for `repo`
   either.

**Decision: the cascade lives in the verb**, ordered
`mailbox_message → session → project_repo → workspace`, inside the store's
single writer transaction. Rehearsed; `foreign_key_check` clean.

`ix_repo_common_dir` is added because D48 makes `git_common_dir` the binding key
and `find_repo_by_common_dir` is a full table scan today (`reads.py:74-76`).
Cheap, and the table is open anyway.

### `Unassigned`

- Reserved id, the literal string `"unassigned"`. `workspace.id` has no format
  constraint, and a sentinel that reads as itself in a log beats a ULID nobody
  can recognise.
- Seeded by the migration, so `session.workspace_id NOT NULL` is satisfiable
  from the first moment a session can be orphaned.
- `rename_project` and `delete_project` **refuse** it. `add_repo` refuses it too:
  a project defined by repo paths is the thing `Unassigned` is the absence of.

### Binding, after the join table

`bind_cwd_to_repo`'s steady-state branch (`binding.py:240-247`) reads
`known.workspace_id` off the repo row. That column is gone, so the branch
resolves the project through `project_repo`:

| Repo is in… | Project chosen | Why |
|---|---|---|
| exactly one project | that one | unambiguous |
| more than one project | `Unassigned` | D60: a discovered session cannot be asked, so it degrades rather than being attributed to whichever row the join returned first |
| no project (orphaned repo) | `Unassigned` | D59 |

The other three branches — not-a-repo, bare repo, new repo — stop auto-creating
a project and bind to `Unassigned` (D59). That is the single chokepoint D59 asks
for, and it is also D62's switch (3).

**Orphaned `repo` rows are kept** when their last project is deleted. They are
unreachable through `list_repos` (which is per-project), they cost one row, and
keeping them preserves the `git_common_dir` ↔ `root_path` identity so that
re-adding the same path later rebinds to the same repo instead of minting a
second one under the `ux_repo_path` unique index.

### The five verbs, plus two the recon says are missing

| Verb | blast_class | Note |
|---|---|---|
| `create_project` | `local_destructive` | D58 |
| `rename_project` | `local_write` | a label change; reads are not destructive |
| `delete_project` | `local_destructive` | D61's three-way choice |
| `add_repo` | `local_destructive` | D58 — it widens §13's allowlist |
| `remove_repo` | `local_write` | it narrows the allowlist |
| `list_repos` | `local_read` | **exists in the store, has no tool and no route** — the UI cannot see a project's repos at all |
| `get_project` | `local_read` | **new**: `admission.py` scans `list_workspaces()` and filters in Python because no by-id verb exists |

`delete_project` takes an explicit `on_running` argument — `refuse` (default),
`kill`, `orphan`. Default-refuse means the three-way choice cannot be skipped by
omission, which is the whole point of D61.

### The defect D57 names

`upsert_workspace` matches `WHERE name = ?` (`writes.py:104-118`) and the name
comes from `Path(path).name` (`binding.py:203-205`). **Both halves go**:
identity becomes `workspace.id`, and discovery stops minting names from
basenames because it stops creating projects at all.

### Two live defects found by the recon, not in the backlog

1. **`workspace.last_activity_at` is never written by anything in `src/`** — it
   is always NULL, and `project_workspace()` (`tools_m1.py:150-159`) projects it
   to the UI and the master anyway. Either fill it or stop rendering it. This
   design fills it, from the project's most recent session event, because the
   Projects page sorts on it.
2. **`discover_repos()` has no caller in `src/`** (`discovery.py:28-66`) and its
   module docstring cites `workspace.root_path` as its reason to exist. Removing
   the column makes that docstring false. Decide in the plan: wire it to
   `add_repo` as a directory-scan helper, or delete it with its test file.
   Leaving a false docstring behind is not an option.

---

## Approach chosen — sub-project 2

### File layout

The prototype is one 3,855-line file: 1,841 lines of CSS, ~280 of markup, ~1,670
of script. It ships as the existing module shape, not as one file:

| Path | Was | Becomes |
|---|---|---|
| `index.html` | 3 views, rail slot above `<main>` | shell: side pane, header, six page roots, three dialogs |
| `app.css` | 582 lines, no reset, no tokens | the redesign's stylesheet, token layer first |
| `app.js` | bootstrap + nav | bootstrap + pane/drawer + page routing |
| `fleet.js` | fleet page | **flock.js** — three panes |
| `chat.js` | chat + audit tail | **keeps its filename** (see below) — conversation only; the audit tail moves to Settings (U6) |
| `session.js`, `terminal.js`, `sse.js` | unchanged in role | restyled, same contracts |
| `rail.js` | the Needs-You rail | **deleted** — see below |
| `escape.js` | dead, nothing imports it | deleted |
| *(new)* `projects.js`, `settings.js` | — | the two new pages |

### `chat.js` keeps its name — the freeze pins it

`fleet.js` → `flock.js` is fine. **`chat.js` → `shepherd.js` is not**, and this
was found by simulating the gate rather than by reading it.

`chat.js` is the only static file created *after* the step-0b baseline, and
T24's rebase claimed it. Deleting it makes it absent from both `baseline` and
`files`, which `moved_paths` reads as **not moved** — while
`rebase.regenerated_paths` permanently asserts it moved. The equality fails with
`declared-but-not-moved = ['web/static/chat.js']`, and it cannot be repaired:
declaring it in `post_milestone` trips disjointness, and the rebase block may
not be rewritten.

So the module keeps the filename and the page is called Shepherd. A module
filename is not a user-facing label, and the alternative is either a broken gate
or a rewritten re-base that was explicitly spent once. Recon §I carries the
measured table of which files can move.

### Three things in the prototype that must NOT be ported

1. **The client-side sort.** The prototype carries `BUCKET_ORDER` and
   `fleetSortKey`. `tests/web/test_palette.py::test_the_page_does_not_re_derive_the_order`
   bans `.sort(`, `localeCompare` and the literal `BUCKET_ORDER` from the page,
   and it is right: `fleet_tree` already orders by `fleet_bucket_sort_key`
   (`tools_m1.py:336`). **The owner's "order by some rule" is already satisfied
   server-side.** The page renders the order it is handed.
2. **The Google Fonts link.** This server binds loopback only and must work
   offline; a remote font is a third-party request from a local tool and a
   render stall on a slow network. `_CONTENT_TYPES` cannot host one locally
   either. Dropped for a system stack; the design's choices survive as
   fallbacks.
3. **The artifact wrapper's `[hidden]` reset.** It must be written into
   `app.css` explicitly (U18). The recon found this is **already a live bug** in
   the shipped page — `.chat-view` is `display: grid` and only stays hidden
   because JS also sets `.hidden`.

### The rail (U2) — a reversal that needs a decision row

U2 takes the Needs-You rail off the shell. `tests/web/test_rail.py::test_rail_is_on_every_page`
asserts the slot sits in `index.html` before `<main>`, and that test encodes
§12's *"on every page"*. Removing it reverses a spec decision.

**It gets a numbered decision row (D66) in spec §3, and §12's rail section is
rewritten to point at it.** Deleting the assertion quietly is exactly what §0
forbids. `rail.js` already carries a `post_milestone` entry from the 2026-09-20
scrub whose `why` says *"comment text only… no behaviour changed"*; that entry
must be **rewritten** to describe the path's full divergence from baseline,
because entries are per path, not per edit, and the old sentence stops being
true.

### The renames

`stranded`, `limit exceeded`, `unknown` change in **`core.stops.PALETTE`**
(`stops.py:267-280`), not in a UI table. `test_palette_matches_core_stops` then
passes unchanged, because it compares the page against `PALETTE` — which is the
drift it exists to catch. `Bucket` *values* do not move, so `stop_rules.py`, the
store and the 90-day log are untouched.

### U17 — the decision card

Parse `{text, choices[]}` off a pane snapshot, built against
`docs/probes/2026-09-14-schemas/tmux-tui/`. Three degradations, all mandatory:
attached sessions render read-only (no pty of ours); anything unparseable falls
back to the ask plus approve/reject, **never a guess**; and C15's trust dialog
is recognised explicitly, because a blind Enter there answers *"No, exit"*.

## Error handling

- Tool handler exceptions become `"request failed (correlation_id=…)"`
  (`registry.py:69`). The pages surface the correlation id — it is the only
  thread back to the failure ring.
- `bind_cwd_to_repo` never raises (`binding.py:213`). That contract is kept.
- A delete refused for running sessions is a **refusal with a list**, not an
  error: the page renders the three choices from it.
- An unparseable decision prompt degrades; it never guesses.

## Testing strategy

- Unit + store verb tests per phase, TDD through `component-builder`.
- The `/work/api` vs `/personal/api` collision gets a test that **fails against
  today's code** before the fix lands.
- Migration 004 gets an apply-and-`foreign_key_check` test plus a forward-only
  test that pins 001–003's recorded sha256.
- `tools/render_check.py` runs against the **served** page (a real `controld`
  on loopback), not the prototype file.
- QA route with Playwright over the composed system, after BUILD.

## Observability

`unknown`-rate and anomaly counters already exist and are unchanged. The
Projects page adds no counters. D62's three switches are written as switches
but ship on, per the decision.

## Questions resolved

| Q | Answer |
|---|---|
| `ON DELETE CASCADE` or cascade in the verb? | **The verb.** The DB cannot express D61's three-way choice, and a schema cascade is a silent destroyer. Probed: no `session` rebuild needed. |
| Does `DROP COLUMN` work on an FK-referencing column? | **Yes**, SQLite 3.45.1, probed. The assumed rebuild of `repo` is unnecessary. |
| How is `Unassigned` identified? | Reserved id `"unassigned"`, seeded by the migration, refused by rename/delete/add_repo. |
| Which project when a repo is in several? | `Unassigned` for a discovered session (D60). Explicit at spawn otherwise. |
| Orphaned repo rows on delete? | Kept — preserves D48 binding identity under `ux_repo_path`. |
| Does the page sort? | **No.** The server already orders by `fleet_bucket_sort_key`. |
| Webfont? | Dropped. Loopback-only, must work offline, and `_CONTENT_TYPES` cannot host one. |
| Rail? | Off the shell, with a numbered decision row (D66) and a rewritten `post_milestone` entry. |

## Domain glossary

| Term | Meaning |
|---|---|
| **project** | The consumer-facing word for a `workspace` row (D22). A name, a description, and a set of repo paths — nothing else (D57). |
| **Unassigned** | The reserved project holding work that matched no declared project (D59). Not a real project: cannot be renamed, deleted, or given repos. |
| **Flock** | The sessions page. Was "fleet", briefly "herd". |
| **stranded** | Printed label for bucket `unfinished`: it stopped and will never resume on its own. |
| **limit exceeded** | Printed label for bucket `paused`: exactly `rate_limited` and `quota_paused`. |
| **the ask** | The engine's own prompt text, shown verbatim on a `needs_you` card (U7, U11). |

## Decisions / ADR notes

| Chosen | Rejected | Why |
|---|---|---|
| Cascade in the verb | `ON DELETE CASCADE` | needs a 40-column table rebuild, cannot express D61's choice, and arms a silent destroyer |
| Sentinel id `"unassigned"` | a ULID | recognisable in a log; `id` has no format constraint |
| Keep orphaned repo rows | delete them | preserves D48 binding identity under the unique path index |
| Server-side ordering only | port the prototype's sort | a page that re-derives the order is a second source of truth; a shipped test already forbids it |
| System font stack | Google Fonts | loopback-only, offline-capable, and the server cannot host a font file |
| `rename_project` is `local_write` | `local_destructive` | it changes a label; D58 names the destructive three and this is not one |
| `delete_project(on_running="refuse")` default | an `force` boolean | default-refuse makes the three-way choice unskippable by omission |

### Brainstorming Handoff (MACHINE-READABLE)

```yaml
DESIGN_FILE: "/root/Shepherd/docs/plans/2026-09-21-projects-and-ui-design.md"
DESIGN_SUMMARY: "Projects become declared objects with a lifecycle (migration 004, a repo-project join table, seven verbs, a reserved Unassigned project, verb-side delete cascade), then the web UI is replaced by the dark-only redesign across Shepherd, Flock, Projects and Settings."
MEMORY_NOTES:
  glossary:
    - term: "Unassigned"
      meaning: "Reserved project id 'unassigned', seeded by migration 004, holding work that matched no declared project. Cannot be renamed, deleted, or given repos."
    - term: "project"
      meaning: "A workspace row seen by a consumer: name, description, and a set of repo paths. D57 removed root_path."
  decisions:
    - decision: "D61's delete cascade lives in the verb, not in an ON DELETE CASCADE clause."
      rejected: "Adding ON DELETE CASCADE to session.workspace_id."
      why: "SQLite cannot ALTER an FK, so it needs a 40-column session rebuild; the DB cannot express D61's kill/orphan/cancel choice anyway; and a schema cascade silently destroys sessions on any future accidental delete."
    - decision: "Migration 004 uses ALTER TABLE DROP COLUMN for repo.workspace_id and workspace.root_path."
      rejected: "Rebuilding both tables the way migration 002 rebuilt session."
      why: "Probed against SQLite 3.45.1: DROP COLUMN succeeds on the FK-referencing side. The assumed rebuild was unnecessary risk."
    - decision: "The page never sorts; the server's fleet_bucket_sort_key is the only order."
      rejected: "Porting the prototype's client-side BUCKET_ORDER and fleetSortKey."
      why: "tests/web/test_palette.py::test_the_page_does_not_re_derive_the_order already forbids it, and fleet_tree orders server-side today."
    - decision: "Drop the Google Fonts link for a system font stack."
      rejected: "Keeping the prototype's webfont."
      why: "The server binds loopback only and must work offline; web/server.py is byte-pinned and its content-type table cannot host a font file locally."
```
