# QA remediation — eleven defects, and the two that misled a person about a delete

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: qa-executor)
- Base: `a095138` on `integration`
- Python: `/root/Shepherd/.venv/bin/python`
- Scope: `src/shepherd/web/static/` and its tests. `tools/` and
  `tests/web/test_render_live.py` belong to another agent and are untouched.
- Files touched: `web/static/projects.js`, `web/static/app.js`,
  `web/static/chat.js`, `web/static/settings.js`, `web/static/index.html`,
  `web/static/app.css`, `tests/web/test_projects_page.py`,
  `tests/web/test_shell_live.py`, `tests/web/test_frontend_unreachable_daemon.py`
  (new), `tests/web/fixtures/unreachable_fetch.js` (new),
  `tests/boundaries/consumer_manifest.json` (digests only) — and this file.
- The tree was **2165 green** and `mypy --strict` clean before a line of this
  was written. Nothing here was red. What is fixed is unearned green.

## Why none of this was caught, stated first because it is the reusable part

Everything in `tests/web/` seeds **one project and at most two sessions**
(`conftest.seed`: one `create_project`, one `register_session`). Every running
session in the tree was *attached*, so `runner_handle` was NULL on all of them
and `DeletePlan.killable` was empty in every test that ever read it. No two
projects ever shared a name. No path was long enough to ellipsise. No envelope
was ever published at a rate.

QA found eleven defects by seeding a product instead: several projects,
sessions in all eight buckets, a 120-character repo path, a 200-character
title, two projects called the same thing, and a hundred envelopes through the
real ring. **Nine of the eleven are invisible at n=1.** The seeding helpers are
now committed — `seed_several_projects` and `owned_session` in
`tests/web/test_projects_page.py`, `publish_events` in
`tests/web/test_shell_live.py` — so the next page is proved against a populated
one.

## The ledger

| # | Sev | Defect | Fix | Test that would have caught it |
|---|---|---|---|---|
| **1** | HIGH | the delete dialog said *"6 session records"* over a delete whose own record said `doomed: [8 ids]`. `commit_project_delete` runs `DELETE FROM session WHERE workspace_id = ?` — the **running** rows go too. `endedSessions()` filtered `ended_at !== null` and showed the complement, which is the count for the **orphan** branch presented as the unconditional one | `endedSessions` is **deleted**, not corrected. Before the button the sentence counts every session record in the project — the one derivation that agrees with the DELETE statement — and the moment `doomed` exists (the first refusal) the dialog renders the server's list and the server's count, in the same words | `test_the_delete_dialog_counts_every_session_record_the_delete_takes` |
| **2** | HIGH | a rejected `fetch` walked past every refusal path in four of six modules. With `controld` stopped, Create left the dialog open, `#p-refusal` hidden and empty, and an unhandled `Failed to fetch` on the console. `projects.js` **ships an element built for exactly this** (`:443-447`) and never reached it | the whole call is inside a `try` in `app.js`, `projects.js`, `settings.js` and `chat.js`, in `session.js`'s shape and with its copy. The gate is **systemic**, not four patches: `test_frontend_unreachable_daemon.py` walks the braces of every module the server serves | `test_a_create_that_never_reaches_the_server_says_so`, `test_the_shell_says_when_a_read_never_reaches_the_server`, and the scan over all six |
| **3** | MED | `set_project_description` is built, routed, registered and works — and the page disabled the field saying *"no verb changes it in this build"*. That sentence told a person that fixing a typo meant **deleting the project** | the field is live and Save issues `POST …/description` when it changed, and only then. Absent clears it, as at creation | `test_the_edit_dialog_changes_the_description` |
| **4** | MED | the server sends `killable: []` / `unkillable: [ids]` — it already knows the stop cannot reach anything — and the page offered *"Stop them, then delete"* as the primary danger choice anyway | the choice is rendered from the split: disabled with a reason when `killable` is empty, and when it is mixed the note **names the sessions it cannot reach** instead of letting the click discover them | `test_the_stop_choice_is_refused_in_advance_when_nothing_is_killable` and its other branch, `…_is_offered_when_the_server_says_one_is_killable` |
| **5** | MED | `#stream-status` had three writers and three vocabularies: `sse.js`'s `live`/`reconnecting`/`unreadable`, `app.js:213`'s **raw event kind**, and `app.js:65`'s error-plus-correlation-id. Measured in one load: `live` → `no such session: …` → `qa.burst`. The connection indicator was destroyed by the first event, and the only place a correlation id is ever shown survived ~35ms | two slots. `#stream-status` is the stream's state and **only `connect()` writes it**; `#stream-message` holds errors and persists until another error replaces it or the button dismisses it. The envelope's `type` is written nowhere | `test_the_connection_state_is_not_destroyed_by_the_first_event`, `test_an_error_persists_until_it_is_superseded_or_dismissed` |
| **6** | MED | two rows reading `twin`, separable only by *"0 repos"*, and a delete dialog reading **"Delete twin"** with no id, no path, no count | the id is shown on list rows whose name is **not unique** (always would be noise), and the delete dialog carries `#dlg-delete-identity`: the id, the description and the repo paths. On create, a name that already exists **warns once and creates on the second press** — E1 makes a duplicate a real intent, so it is a warning and not a refusal | `test_the_delete_dialog_names_the_project_by_more_than_its_name`, `test_a_duplicate_name_is_warned_about_before_a_second_project_is_made` |
| **7** | MED | two rapid clicks: the first delete succeeded, the second raced and lost, and the last sentence on screen was *"there is no project '<ULID>' to delete"* — a failure, naming a raw id, **about a delete that worked**. One run in two | an in-flight flag (not a disabled button: the choices are rebuilt on every answer, so a disabled node is replaced before the second click lands), and the refusal branch re-reads the list before it writes anything into the dialog | `test_a_second_delete_click_cannot_race_the_first`, asserted on the wire |
| **8** | LOW | 1/10/100 envelopes → 4/40/400 requests, perfectly linear, ~115 req/s from one tab against a store with one writer thread | the refresh is coalesced: an envelope arriving during a refresh marks it stale rather than starting a second one, so a burst of N costs two passes. Still no timer — §12 forbids a schedule, not a merge | `test_a_burst_of_envelopes_does_not_become_a_request_per_envelope` (40 envelopes, ceiling 16) |
| **10** | LOW | a whitespace-only name passes `required`, then `onProjectSubmit` trimmed it to `""` and `return`ed with **no message at all** | the refusal line says so | `test_a_whitespace_only_name_is_refused_with_a_sentence` |
| **11** | LOW | a 935px repo path in a 334px box and a 1366px title in a 266px one, neither carrying `title` — so the ellipsised half of a §13 allowlist path could not be read by any means the page offered | a `titled()` constructor; `title === textContent` on every name, heading, path and session title | `test_every_value_that_can_be_truncated_carries_its_full_text_as_a_title` (a sweep over four selectors, so a later element that truncates and forgets is caught by the same line) |

Defect **9** is not in QA's report and is not in this table; the numbering is
theirs and is kept rather than re-flowed.

## Two tests were rewritten, and the reason is the fix

`test_a_kill_that_does_not_land_keeps_the_project_and_says_so` and
`test_a_partly_landed_kill_shows_what_it_stopped_on_the_refusal` both **clicked
"Stop them, then delete"** on projects whose every session was attached — which
is exactly the plan that defect 4 says the page must not offer. They were green
because the page offered it unconditionally.

They now use `owned_session`, which sets `runner_handle` the way `spawn` does.
Nothing was weakened: the first still proves that an injected kill which reports
`False` leaves the project standing and says which sessions survived, and the
second still proves `killed` is rendered on a **refusal**. What changed is that
the row on which the click is made now looks like the row production would let
you click on. Both keep their frozen node ids — bodies were rewritten, nothing
was renamed or deleted, so no `RETIRED_NODE_IDS` entry is owed.

## The gate that is seen to fail, and what it cannot see

`test_frontend_unreachable_daemon.py` blanks comments and string literals
(length-preserving, so offsets stay real), walks the braces, and reports every
`fetch(` not lexically inside a `try`. Three controls, because a scan is worth
what its scope is worth:

1. `test_the_caller_set_is_exactly_the_modules_that_call_fetch` — the closed set
   is checked **against the directory**, so a seventh module that talks to the
   API cannot be certified by never being looked at.
2. `test_the_gate_catches_an_unguarded_fetch` — `fixtures/unreachable_fetch.js`,
   an inert file nothing imports, holds one guarded call, one unguarded one, and
   the three shapes the scanner must be blind to (`fetch(` in a string, `fetch(`
   in a comment, a `}` inside a string). The gate must name **exactly** the
   unguarded line.
3. It was **observed red on the real tree**: at the moment it was written it
   named `chat.js` and `settings.js` and passed the other four, which is the
   split QA's table predicted.

What it cannot see is whether the `catch` does anything. A silent `catch {}`
satisfies it. That half is behaviour, and it is proved in a browser against an
aborted route in `test_projects_page.py` and `test_shell_live.py`, which read
the sentence off the page.

## Gate A

`app.js`, `app.css`, `chat.js` and `index.html` are in
`rebase.regenerated_paths`; `projects.js` and `settings.js` already have
`post_milestone.edits` entries. All six are **digest updates only** — no entry
was added and no second entry created, per the rule that entries are per path.
`sse.js`, `flock.js`, `session.js` and `terminal.js` were deliberately not
touched: defect 5 could have been fixed in `sse.js` and was fixed in `app.js`
instead, because the stream module's contract (`onStatus` is the connection
state) was already right and it is the bootstrap that was overloading the slot.
