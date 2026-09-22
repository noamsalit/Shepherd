# T3.4 — remediation: the kill that escaped, and the five gaps the first consumer found

`wf-20260921T212808Z-9172ed6b` · branch `integration` · main checkout
Python `/root/Shepherd/.venv/bin/python`

Origin: code review of Phase 9 (`5ab3668`, *"all seven verbs are drivable, and
the first consumer found five gaps"*). Scope: `toolsurface/`, `store/`,
`web/routes.py` and their tests. **`web/static/` untouched** — four other
builders were in worktrees on it, and three of their merges landed in this
checkout mid-run (see §Concurrency).

Every check below was run in this session. Every fix was driven by a test that
was seen to fail first, and every gate was planted against and seen to bite
(§Mutation ledger).

---

## 1 — BLOCKING: a raising kill escaped the verb after real kills

`tools_projects.py:248-252` stopped sessions inside a generator expression.
`kill` is allowed to raise and the shipped one does: `runner/local.py:478`
raises `RunnerRefusal` for a **stale handle** — a row whose `ended_at` is still
NULL while its pane is gone — and `plan.running` **is** `ended_at IS NULL`, so
that row is exactly what the loop was handed.

RED, before any fix (`tests/toolsurface/test_tools_projects.py::
test_delete_project_treats_a_raising_kill_as_did_not_land`, exit 1):

```
AssertionError: ('request failed (correlation_id=cid-h)', <Failure.FAILED: 'failed'>)
```

That is the measured blocker: the escape reaches `registry.py:466`, which
flattens it to `GENERIC_ERROR`, and a page renders **"request failed"** for a
call that just stopped a live agent.

**Fix.** `_kill_running` catches per session, treats a raise as **did-not-land**,
counts it (`AnomalyKind.STOP_FAILED` — the kind already means *a stop that
failed*; no new member was minted, which would have been out of scope), names it
on the record as `kill_failures: [{"session_id", "reason"}]`, and lets
`commit_project_delete` decide on the store's own `ended_at` fact.

Measured, three sessions with the second raising: `killed == [first, third]`,
`running == [second]`, `kill_failures == [{"session_id": second, "reason":
"RunnerRefusal: tmux refused"}]`, project intact, `stop_failed` count 1.

**What this does not prove.** It does not prove the *shipped* kill raises only
`RunnerRefusal` — the catch is `except Exception` precisely because it cannot.
It does not prove anything about a kill that hangs: a callable that never
returns still blocks the verb, and no timeout was added. And `kill_failures` is
a tool-layer record: `DeleteOutcome` is unchanged, because the store never saw
the raise.

## 2 — GAP 1: `doomed` never reached anyone

`reads.plan_project_delete` computed `doomed` **after** the refusing return, so
the one record a page holds *before the button* carried an empty tuple. Moved
above the return. Under `REFUSE` it is every session row in the project (what
goes if the caller proceeds); the orphan case is that list minus `running`,
which the caller holds in the same record. The handler now passes the **plan**
to `delete_outcome`, not only its refusal.

Not proved: that any page reads it. Phase 10 owns that.

## 3 — GAP 2: `running` did not distinguish killable from unkillable

`DeletePlan` gains `killable` / `unkillable`, split on `runner_handle IS NOT
NULL` — which is exactly the question `handle_for` asks before the shipped kill
answers `no_pane(...)`. Derived in the read, where the rows are already loaded,
so it is not an N+1. Both branches are asserted (an attached session is
unkillable; one with a handle is killable).

Not proved: that a handle means the kill *will* land. It means the kill path has
a pane to address. A stale handle is still a `RunnerRefusal`, which is §1.

## 4 — GAP 3: no verb changed a description

**Decision: a new verb, not a widened `rename_project`.** A verb called *rename*
that edits a description is a verb whose name is wrong, and a two-field verb has
to invent a spelling for "leave this one alone" — absent-means-unchanged beside
null-means-clear — at the one surface where clearing is a real intent.

**Named `set_project_description`, not `set_description`**: the registry is flat
and global (`rename_session` and `rename_project` are both in it), and a
description is a field more than one thing has.

Absent **clears** it, at the route and at the handler. Reserved project raises
(E8); missing project answers `None`; both become this family's one refusal
record.

### The four counts a new POST route moves

Re-derived from the tables, not copied. All four stated numbers were right:

| count | was | is |
| --- | --- | --- |
| `len(routes.POST_ROUTES)` | 15 | 16 |
| `len(routes.BODY_ARGS)` | 15 | 16 |
| body-gate arrival (`checked == len(POST_ROUTES) - 1`) | 14 | 15 |
| `PROJECT_TOOL_NAMES` | 7 | 8 |

Plus `PROJECT_TOOL_NAMES_HERE` in `test_compose.py` (7 → 8) and
`PROJECT_POST_ROUTES` in `test_routes_projects.py` (5 → 6), both written-out
lists that must be **admitted** rather than derived.

## 5 — GAP 4: D60 was unreachable

`reads.projects_by_repo()` answers `{repo_id: every project holding it}` in one
statement — the population `projects_for_repo` answers one at a time, which is
right for `bind_cwd_to_repo` and an N+1 for a page. `project_repo_row` carries
`projects`, on both read verbs, with **every** holder including the current
project: "shared with" is the page's word for the rest of the list, and a
projection that pre-subtracted would make one list mean two things in two
places.

## 6 — `resolve`'s query args no longer override the path parameter

`resolve` merged the query **after** the captured path while `resolve_post` did
the opposite. Nothing was exploitable — no GET template collides with its own
`QUERY_ARGS` — but `routes.py:117` states the invariant table-wide and it was
held by the *absence of a collision*. Mirrored, with the POST twin's test shape:
declare the field for one route, watch the URL win.

## 7 — the shadow guard is derived from the table

It enumerated two names (`routes.SESSION_ID`, `routes.PROJECT_ID`) of the three
path parameters the table has — `approval_id` was covered by a comment — and was
keyed on constants **no production code reads**, so a typo made it vacuous and
green. It now extracts each template's `{…}` segments and checks them against
that template's own fields, over `BODY_ARGS` **and** `QUERY_ARGS`.
`routes.PROJECT_ID` is deleted with the enumeration that read it; `SESSION_ID`
stays because `resolve_terminal` reads it.

The gate is **seen to fail** on the case the enumeration survived
(`test_the_shadow_guard_catches_the_parameter_the_enumeration_missed`).

## 8 — `kill_landed` is a named function with a test

Hoisted out of `compose.py`'s closure and asserted over **both real answers**:
`kill_landed(kill(...)) is True`, `kill_landed(no_pane("s-1")) is False`, and
the real `no_pane` answer `kill_session` gives for an unknown session.

**Deviation:** it lives in `tools_terminal.py` beside `no_pane`, not in
`tools_m3.py` beside `kill`. `tools_m3.py` is at 445 of the 450-line cap and the
docstring does not fit under it. Stated in the docstring and in the test.

## 9 — the cap gate globs, and found four modules it had never measured

`test_the_three_modules_are_each_under_the_cap` built `sizes` from a seven-path
tuple and asserted `len(sizes) == 7`. Replaced by
`test_every_tool_module_is_under_the_cap`, which globs `tools_*.py` (plus the
named `spawn_origin.py`) and keeps an explicit `CAPPED_MODULE_COUNT` so a new
module must be **admitted**.

The glob reached four modules the enumeration never measured —
`tools_engine.py` (118), `tools_hooks.py` (115), `tools_replay.py` (127), and
two **over the cap**: `tools_m1.py` (574) and `tools_master.py` (505). They are
grandfathered *by name and pinned at their current size*: exempt from 450, not
from growth. Widening the cap for everyone would have retired the gate.

The count gate was seen to fail on a real new module: adding
`tools_projects_delete.py` turned it red at `13 == 12` before it was admitted.

### Two splits the caps forced, both named

| module | why | sizes |
| --- | --- | --- |
| `toolsurface/tools_projects_delete.py` | §1's fix did not fit under 450; the cut is where the effect leaves the process | `tools_projects.py` 441 → 386, new module 250 |
| `store/projects.py` | `set_project_description` took `writes.py` to 623 against the 600 every file in `src/` is held to; the sibling pattern `sessions.py`/`stops.py` already uses | `writes.py` 623 → 302, new module 366 |

`store/projects.py` holds D57's family and **`writes.py` no longer holds any of
it** — asserted both ways in `test_the_m1_and_m2_write_implementations_live_in
_store_writes`, so one verb cannot become two bodies that drift.

---

## Mutation ledger

`__pycache__` cleared before every run (CLAUDE.md rule 4). Committed first,
planted, reverted by path. Eight mutations, eight REDs, no survivors.

| # | mutation | target | result |
| --- | --- | --- | --- |
| M1 | the kill escapes again (generator, no catch) | `test_..._raising_kill_...` | RED (exit 1) |
| M2 | the anomaly is not counted | same | RED (exit 1) |
| M3 | `doomed` dropped from the refusing plan | `test_the_refusing_plan_...` | RED (exit 1) |
| M4 | `killable` / `unkillable` swapped | `test_a_refused_delete_...`, `test_a_session_with_a_pane_...` | RED (exit 1) |
| M5 | `resolve` merges the query last again | `test_..._query_that_names_another_session` | RED (exit 1) |
| M6 | `kill_landed` always answers `True` | `test_kill_landed_...` | RED (exit 1) |
| M7 | the repo projection drops its holders | `test_a_repo_projection_names_...` | RED (exit 1) |
| M8 | `set_project_description` writes the `name` column | `test_set_project_description_...` | RED (exit 1) |

## Retired node ids

Two, both recorded in `RETIRED_NODE_IDS` with a reason and a named successor,
because the frozen baseline is a subset check and a rename reads as a deletion:

- `test_the_three_modules_are_each_under_the_cap` → `test_every_tool_module_is_under_the_cap`
- `test_no_body_field_shadows_a_path_parameter` → `test_no_declared_field_shadows_a_path_parameter`

Both were renamed rather than edited in place because the **subject** changed,
and a reader who meets the old name in a log is looking at a different property.

## Gate A (`web/routes.py` byte freeze)

The digest in `files` is updated twice and **no `post_milestone` entry is
added**: `web/routes.py` is already in `rebase.regenerated_paths`, and the
disjointness assertion forbids relaundering it. Same handling as Phase 4
(`a88ce91`), which recorded the same reasoning.

## Concurrency

Three merges from other builders landed in this checkout **during** the run
(`d94382d` Phase 6, `63d181e` Phase 7, `ba41d24` Phase 9 — the Projects page),
one of them leaving conflict markers in `tests/web/test_frontend_escaping.py`
while it was being resolved. No commit was made while `MERGE_HEAD` existed, and
nothing under `web/static/` was touched.

**Three failures are left in the tree and none of them is this task's.** All
three name `web/static/*.js` files and nothing else:

- `test_completing_l4_changed_no_consumer_byte` — *files added under web/ or
  cli/ since the freeze: `['web/static/flock.js', 'web/static/projects.js',
  'web/static/settings.js']`*. Their owners must declare them; `web/routes.py`
  is recorded here.
- `test_the_pending_wiring_list_is_exactly_what_is_owed` — `web/static/fleet.js`
  is gone (renamed to `flock.js` by Phase 6).
- `test_every_shipped_module_is_reachable_from_the_page` — the shell imports
  none of `./flock.js`, `./settings.js`, `./projects.js` yet.

Everything in this task's scope is green: `tests/store`, `tests/toolsurface`,
`tests/boundaries` (bar the Gate A row above), `tests/web/test_routes_m3.py`,
`tests/web/test_routes_projects.py`, and `mypy --strict src/shepherd` over 130
files.
