# QA remediation, second pass — the reason a stop refused, and create's missing guard

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: qa-executor)
- Base: `3030b6b` on `integration`
- Python: `/root/Shepherd/.venv/bin/python`
- Files touched: `web/static/projects.js`, `web/static/app.css`,
  `tests/web/test_projects_page.py`, `tests/boundaries/consumer_manifest.json`
  (two digests, **no new `post_milestone` entry**) — and this file.
- Before: **2187 passed, 2 skipped**, `mypy --strict` clean over 130 files, 105
  boundary rules green. Nothing here was red; what is fixed is unearned green.

QA re-ran against the eleven-defect remediation, closed all eleven, and found
two more on ground the first pass had only just made reachable. Both are below.
The third item is a finding about QA's own harness and resolves to *no committed
test carries that shape* — proved rather than asserted.

## The ledger

| # | Sev | Defect | Fix | Test that would have caught it |
|---|---|---|---|---|
| **1** | HIGH | the server says **why** a stop did not take and the page discarded it. Over a project holding a session Shepherd owns, the kill reached tmux and refused; the record carried `kill_failures: [{session_id, reason: "RunnerRefusal: tmux exited 1 … error connecting to /tmp/tmux-0/shepherd-runner"}]` and `bump_anomaly(STOP_FAILED)` had fired. The dialog said only *"2 session(s) … were not stopped; nothing was deleted"*. `grep -n kill_failures web/static/*.js` → no match. `tools_projects_delete.py`'s own docstring states the field exists so *"a refusal that says '1 session is still running' can also say why the stop did not take"* | `renderKillFailures()` — the session id over its reason, at **both** call sites (`#dlg-delete-live` on the refusal, `#dlg-delete-outcome` on the success). The reason is wrapped, not ellipsised: `.dlg-reason` is `white-space: pre-wrap; overflow-wrap: anywhere` in a mono face, because the half of a tmux argv that names the socket is the half that answers the question, and borrowing `.dlg-identity`'s truncation here would have satisfied a "contains the id" assertion while losing it | `test_a_stop_that_refused_names_the_session_and_says_why` and `test_a_delete_that_succeeded_still_says_which_stop_did_not_land` |
| **2** | MED | double-clicking **Create** makes two projects. `inFlight` shipped with **one** key (`delete`) and `onProjectSubmit` never consulted it. The duplicate-name warning does not save it: both POSTs leave before the list is re-read, so `view.projects` never holds the first when the second is decided. QA measured `posts: 2, rows: 2` on 3/3 attempts. **This is defect 7's failure class, fixed on the delete side and left on the create side** | `inFlight.project`, consulted by a thin `onProjectSubmit` wrapper around the old body (now `submitProject`), released in `finally`. A flag and not a disabled button for `inFlight.delete`'s reason plus one more: `#p-save` is a form submit control, and disabling it inside its own handler races the browser's second submit rather than guarding it | `test_a_second_create_click_cannot_make_a_second_project`, asserted on the wire (`len(posted) == 1`) *and* in the store |

### Why `kill_failures` was the only member with no reader

QA enumerated all eleven keys `delete_outcome` emits and counted the page's
readers of each: `deleted` 1, `refused` 5, `running` 5, `killed` 2, `orphaned`
1, `severed` 1, `destroyed` 1, `doomed` 3, `killable` 3, `unkillable` 2,
**`kill_failures` 0**. Exactly one member affected — so this is a single site,
not a systemic pattern, and it was fixed as one.

### Why no committed test could reach it

`_kill_running` has three outcomes and the suite could reach two.
`web/conftest.py`'s `refuses_every_kill` returns `False` (a stop that did not
land and said so); `kills_the_owned_one` returns `True` for one session (a stop
that landed). **`kill_failures` is populated only by the raising branch** — the
branch `runner/local.py` actually takes for a stale handle, a row whose
`ended_at` is still NULL while its pane is gone. The new `the_kill_raises`
fixture is the third injection, and it is the shape the first pass's
`owned_session` helper made reachable.

## The other four unguarded POST handlers — what was chosen, and why

QA swept all eight POST-issuing handlers before reporting: five lack a guard,
but only create produces a **durable wrong row**.

| Handler | Double-click cost | Guarded here? |
|---|---|---|
| `projects.js` create | 2 POSTs, **2 rows** — a second project | **yes** |
| `projects.js` edit (rename / description) | 4 POSTs, 1 row, right description | **yes, by the same wrapper** |
| `projects.js addDraftPath` | 2 POSTs, store stays at 1 repo | no |
| `projects.js removeDraftPath` | idempotent over a `repo_id` already unlinked | no |
| `settings.js choose` | `POST autonomy {level}` twice with the same level | no |
| `chat.js submit` | clears `input.value` before the await, so a second click reads `""` and returns at `chat.js:330` | no |

**Chosen: guard the project submit, leave the other four.** The wrapper covers
create *and* edit because they share one handler and the branch that is about to
issue a request is not known until the name is read — so the count of guarded
handlers is one, not two, which is the honest number.

The four left alone are redundant requests against idempotent verbs. Guarding
them would add four pieces of state in three modules to defend against a defect
none of them has, and this repo's own rule is that **a gate nobody has seen fail
is not a gate** — four flags with no test able to redden them are four claims
that the next reader must re-derive. `chat.js` is the clearest case: its guard
already exists and is not a flag. It is the input it just emptied.

What this decision costs, stated rather than absorbed: if any of those four
verbs later stops being idempotent — a `remove` that decrements a counter, an
`autonomy` that appends an audit row — the guard is not there and the shape is
defect 7's for a third time. The rule that would catch it is *a new POST verb
declares whether a second identical request is a no-op*, and that belongs to
whoever adds one.

## The harness issue — QA's `unreachableControls`, and whether it reached the repo

QA's driver decided reachability from `document.documentElement.scroll*` only.
`div.herd-col` carries `overflow-y: auto`, so it flagged `#proj-new`, two
project rows and five nav items (the *closed drawer*) that are all reachable —
QA proved them reachable by walking the ancestor chain, calling
`scroll_into_view_if_needed` and clicking each. It **over-reports and does not
under-report**, so no PASS rests on it; but every `unreachableControls: 0`
reading in both QA runs is unproven and should be read as such.

**No committed test carries that shape.** Measured, unpiped:

```
$ grep -rn "documentElement\.scroll" tests/            → exit 1 (no match)
$ grep -rn "documentElement" tests/web/                → exit 1 (no match)
$ grep -rn "scrollHeight\|scrollTop\|clientHeight\|scrollWidth" tests/web/
tests/web/test_chat_page.py:524,529,542   (the composer's own growth, asserted as source text)
tests/web/test_decision_live.py:234       ([n.scrollWidth, n.clientWidth] on #session-view)
```

The three near neighbours were opened and are a different claim:

- `tools/render_check.py:368` is `documentElement.scrollWidth - clientWidth` —
  **horizontal** overflow of the document, not reachability of a control.
- `render_check.viewport_faults` measures the **page root's own rectangle**
  (`getBoundingClientRect`) against the viewport, and its docstring already
  refuses to claim anything *inside* the root.
- `test_decision_live.py:234` is element-scoped horizontal overflow on
  `#session-view`, followed by per-slot `bounding_box()` assertions on four
  named nodes — a claim about four elements it names, not a sweep that infers
  unreachability from the document's scroll box.

So: nothing to fix in `tests/web/`, and QA's scratchpad driver is left alone.

## Recorded, not chased

`app_state["kill.<id>"]` records accumulate after a refused kill. By design per
`lifecycle.py` — the write-before-kill order is what survives a crash — but
nothing in the tree was observed cleaning them up. Not in this scope; a store
that only grows is a backlog item, not a defect, until someone measures it.

## Evidence

| Check | Command | Exit |
|---|---|---|
| RED, defect 1 | `pytest tests/web/test_projects_page.py -k says_why` | 1 — `AssertionError: assert 'Not stopped, and why:' in 'Still running:\n01M34R4K628KA0E3C9VHA8D056'` |
| RED, defect 2 | `pytest tests/web/test_projects_page.py -k second_create_click` | 1 — `assert 2 == 1` over `['…/api/projects', '…/api/projects']` |
| RED, defect 1's second call site | same, `-k did_not_land`, with `renderKillFailures(outcome, …)` removed | 1 — `assert 'Not stopped, and why:' in '1 session record destroyed.'` |
| GREEN, all three | `pytest tests/web/test_projects_page.py` | 0 — 31 passed |
| boundaries | `pytest tests/boundaries -q` | 0 (and 1, naming exactly `['web/static/app.css', 'web/static/projects.js']`, before the digests were refreshed — the freeze was seen to bite) |
| whole tree | `pytest -q` | 0 |
| types | `mypy --strict src/` | 0 — 130 files |
