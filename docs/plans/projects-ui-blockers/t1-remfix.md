# T1-remfix — the delete verb's shape, the cascade's blind spot, and six smaller things

Remediation of Phase 1, 2026-09-22. A code review and a failure hunt ran
independently against Phase 1's diff and converged on the same two critical
defects with different probes. The suite was 1947 green throughout. None of
this was red: every item below is **unearned green**.

---

## T1-remfix.1 · `delete_project` deadlocked on a real kill · owner: builder (remediation)

**Symptom.** `writes.delete_project` took `kill: Callable[[str], None]` and
called it from inside the lambda `Store._write` runs — **on the single writer
thread, after `BEGIN IMMEDIATE`**. The real kill path's first statement is a
store write (`orchestration/lifecycle.py:126`, `store.set_app_state(...)`,
whose docstring says write-before-kill is what survives a crash, so it cannot
be reordered). That inner `_write` enqueues and blocks on `done.wait()`, behind
a writer that can never reach it. Daemon thread, no timeout: **every subsequent
write in the process hangs, permanently.** Reproduced by the reviewers'
`probe3.py`:

```
DEADLOCK: delete_project did not return within 10s
```

The second failure needs no deadlock. `kill` is an effect that leaves the
process, issued inside a transaction that can roll back: any later failure in
the same job restores the rows while the panes stay dead, and
`running_sessions_for` then answers with a session whose process was destroyed
— a running card on Flock for a dead agent, indefinitely, with no anomaly
counted. `probe_kill_rollback.py` showed exactly that: *"real processes killed:
['A'] … project 'api' still in the store? True; still listed as running there:
['A']"*.

**What was tried, and what was refused.** Re-entrancy detection in `_write` was
considered and **refused**: it converts a hang into a raise, and the verb
documents *"Never raises"* — the page renders its three choices out of the
refusal, and an exception is not something a card can draw. The fix is a shape
change, not a patch:

* `reads.plan_project_delete(connection, *, workspace_id, on_running) -> DeletePlan`
  — the decision half. The running set, the doomed set, and the whole of the
  refusal. A pure read.
* `writes.commit_project_delete(connection, *, plan, killed=()) -> DeleteOutcome`
  — the commit half. The rows, and only the rows.

The caller kills **between** them, outside any transaction. `Store` carries both
(`plan_project_delete` through `_read`, `commit_project_delete` through
`_write`); `Store.delete_project` and `writes.delete_project` are **withdrawn**.
D33's *"no runner behind a `sqlite3.Connection`"* is now structural rather than
a promise, and the exclusive write lock is no longer held for the duration of N
tmux kills.

**`DeleteOutcome.killed` was reporting kills that did not happen.** A
`Callable[[str], None]` cannot report failure, while the real path answers
`no_pane(session_id)` as a *returned dict* for any session without a runner
handle — which is every **attached** session. After the split the caller knows
which kills landed, and `killed` is what it reports, not what it asked for.

**The cost of the split, named and paid.** The plan is read before the caller
goes away to kill things, so the world can move underneath it. The commit
re-derives the decision inside its own transaction and **refuses** rather than
deleting a session nobody stopped
(`test_the_commit_half_refuses_a_session_that_arrived_after_the_kill`, with the
control: the same call with the newcomer's id in `killed` proceeds).

**Proof.** RED was behavioral and is the property, not the probe:
`test_no_store_verb_takes_a_callable_the_caller_must_run` →
`assert ["Store.delete_project accepts 'kill', a callable"] == []`, exit 1.
End to end, `test_a_kill_between_the_two_halves_may_write_to_the_store` drives
the real first statement of the kill path (`set_app_state`) between the halves
on a worker thread and fails the assertion — rather than hanging the suite — if
it does not return in 10 s. The reviewers' probe, re-pointed at the two halves,
now answers `DeleteOutcome(deleted=True, killed=('01M33…',), destroyed=('01M33…',))`.

**This was also a plan defect**, and the plan now says so in place: line 914
specified the deadlocking wiring (*"`delete_project(on_running="kill")`
delegates to the existing kill path"*). The Out-of-Scope Drift entry for T1.4
records the old wording, the failure, and the replacement, rather than quietly
substituting one for the other. Phase 3's builder has already been told not to
wire it.

**What this does not prove.** Nothing here exercises the *real* kill path:
`lifecycle.record_and_terminate` is not called by any test added here, and no
test asserts that Phase 3's caller kills between the halves — there is no such
caller yet. The seam refuses the old shape; it cannot make the next caller use
the new one correctly.

---

## T1-remfix.2 · the cascade missed the two columns `session` uses on itself · owner: builder (remediation)

**Symptom.** `session` self-references twice — `parent_session_id` and
`retry_of`, both `REFERENCES session(id)` (`001_m1_foundation.sql:58,64`) — with
`PRAGMA foreign_keys=ON`. `DELETE FROM session WHERE workspace_id = ?` is safe
only while every referrer is inside the cohort. Under `ORPHAN` the running rows
are moved out first, so a survivor points at a row the next statement deletes:

```
link=parent_session_id  on_running=orphan  -> RAISED IntegrityError: FOREIGN KEY constraint failed
link=retry_of           on_running=orphan  -> RAISED IntegrityError: FOREIGN KEY constraint failed
```

Seven of nine cells passed, which is the control. A cross-project parent failed
the same way under **any** choice. The reachable case needs nothing exotic: a
spawned or ask-forked child still running while its parent has stopped, and the
user picks *"move them to Unassigned"* — **the dialog asks for the one answer
that throws.** The project is then permanently undeletable, and under `KILL` the
panes are already dead when the rollback undoes the database half.

**Decision applied: NULL the inbound references and report them.** D61 says a
delete **forgets**; a surviving child whose parent was forgotten honestly has no
parent. Refusing would mean saying *"you cannot delete this project because a
session in it once spawned a child"*, which is not a thing to say to someone.
Nulling **silently** is the part avoided: `DeleteOutcome.severed` carries
`SeveredLink(session_id, column)` for every link cut, so the dialog can say it.

**M2, while there.** `ORPHAN` also deletes every *ended* session in the project
and their mailbox rows, and the outcome had no field for them: a user told
`orphaned=('s-live',)` was not told that four hundred finished sessions went
with it. `DeletePlan.doomed` names them **before** the button and
`DeleteOutcome.destroyed` after it.

**Prevention — the part that matters most.**
`test_delete_is_total_over_its_matrix` built a 12-cell product at test time and
called itself total. It was total over the axes it enumerated:
`plant_session` **could not express** `parent_session_id` or `retry_of`, so the
failing input was unreachable from the fixture. The helper now takes both, the
session shape is a **fourth axis** (`LINEAGE_SHAPES`), and **`PRAGMA
foreign_key_check` is asserted empty after every cell** — it was asserted after
the migration and never after the verb that carries the cascade. That check
alone would have found this for free.

P2 is **split out** of the matrix into
`test_no_session_ever_points_at_a_deleted_project`, because a P1 failure masked
it on exactly the cell that raised.

**Proof (mutation).** `__pycache__` cleared first, per the repo rule. With
`_sever_lineage`'s loop emptied (`for column in ():`), both tests go red at
`writes.py:281` with `sqlite3.IntegrityError: FOREIGN KEY constraint failed`,
exit 1; restored, exit 0. The reviewers' 3×3 matrix probe now returns a
`DeleteOutcome` in all nine cells with `foreign_key_check=[]` in all nine.

**What this does not prove.** The severing is proved over the two
self-references only. If a future migration adds a third column referencing
`session(id)`, `LINEAGE_COLUMNS` will not know about it — the `foreign_key_check`
assertion would catch it in the matrix, but only for a shape the fixture can
build.

---

## T1-remfix.3 · `bind_cwd_to_repo`'s "Never raises" was false · owner: builder (remediation)

`run_git` caught `(OSError, subprocess.SubprocessError)`. `subprocess.run(cwd=…)`
raises **`ValueError`** for an embedded NUL, which is neither:

```
NUL byte in cwd -> RAISED ValueError: embedded null byte
```

Four other adversarial cwds returned cleanly and counted, which is the control.
Neither caller wraps it, and `hook_lane._with_foreign_repos` feeds it text
derived from the engine's JSONL. The asymmetry was the tell: `admission.py:180-184`
guards exactly this input by name. `ValueError` joins the except tuple; the
degradation path (`_UNREADABLE_RC`, anomaly counted) was already right. The NUL
row is now a case in AC-8's own matrix test, which went red with
`ValueError: embedded null byte` before the change and green after.

---

## T1-remfix.4 · RD-3 was half-applied · owner: builder (remediation)

`reads.project_last_activity` derived the value correctly and `rows.py:96` went
on mapping the dead column into `Workspace.last_activity_at` — **permanently
`None`** behind a field docstring saying it is *"derived at read time"*. A page
author who believed the docstring would render "never" for every project and no
test would fail. The field and its read are deleted; the column stays in the
schema, unwritten. `test_workspace_carries_no_column_the_store_never_writes`
pins the whole field set, and went red on the field's presence first.

## T1-remfix.5 · two acceptance ids named tests that did not exist · owner: builder (remediation)

AC-4's `test_no_session_ever_points_at_a_deleted_project` and E21's
`test_a_fresh_install_holds_exactly_the_unassigned_project`. AC-4 covers the
plan's highest-rated risk and, run verbatim, exited **4** — the M4 shape, *"the
FAIL named a file nobody built"*. Both now exist under the names the plan cites,
in `tests/store/test_verbs.py`.

## T1-remfix.6 · `reads.py` prescribed an unsound repair · owner: builder (remediation)

`list_workspaces`' docstring told the next author to select a project *"by name
or by a captured id"*. Names are **not** unique (E1; no unique index;
`create_project(name="Unassigned")` mints a second one). "By name" is struck and
the reason is written down. **No** uniqueness constraint was added — that would
contradict D57.

## T1-remfix.7 · the `create_project` non-idempotence repair was inconsistent · owner: builder (remediation)

`tests/store/test_stop_verbs.py:49` and `tests/cli/test_commands.py:32` still
called `create_project` inside `seed()`, and both call `seed()` up to four times
in one test — so the fixtures modelled "four projects, one session each" where
they modelled "one project, four sessions". Nothing was red, and a Flock
grouping test written on that fixture would pass while proving nothing. The
`the_project()` helper — **duplicated verbatim** in `test_tools_m1.py` and
`test_tools_m2.py`, which is why these two were missed — is hoisted to
`tests/project_fixture.py` and used by all four seeds.
`test_no_suite_defines_its_own_copy_of_the_project_helper` refuses the next
copy by property (it went red naming both files), and
`test_the_project_is_the_same_project_every_time` pins idempotence with a
control.

## T1-remfix.8 · the cheap ones · owner: builder (remediation)

* **`project_last_activity` takes a lexical `MAX`.** The fixture planted
  `"2026-01-01T00:00:00Z"` — a spelling no writer in this system produces. It is
  now stamped through `core.clock.stamp` with the two rows differing **inside
  one second**, so the test exercises the format production actually writes.
  **What it does not prove:** the `MAX` is still lexical, and the reviewers'
  `probe_lastactivity.py` still reports `WRONG (the earlier stamp won)` for
  mixed-precision rows. It is correct today only because `core.clock.stamp` is
  fixed width, and `discovery_loop.py:145-147` says of these same stamps that
  they must not be compared as text. Left as-is deliberately (the remit scoped
  this to the fixture); the residual is recorded here rather than closed.
* **`find_repo_by_common_dir` had no `ORDER BY`**, two lines above a docstring
  forbidding unordered reads — and Phase 1 raised the stakes, since the project
  is now derived from whichever row comes back. `ORDER BY root_path` added.
* **`Store._write` could block forever if `close()` won the window** between the
  `_closed` check and the `put`. The check and the put are now one critical
  section under `_close_lock` — the option the remit offered as an alternative
  to a `done.wait()` timeout, chosen because it makes the failure impossible
  rather than bounded. **What it does not prove:** the probe that modelled the
  window (`probe_close_race.py`) parks *inside* `put`, which an unbounded
  `queue.Queue` never does — and under the fix that park deadlocks `close()`
  instead, because `close()` now waits for the same lock. So the probe cannot be
  re-run as written; `test_no_write_hangs_when_close_races_it` bounds it
  instead (eight writers racing a `close()`, each of which must return a result
  or `RuntimeError`), and that test would **not** reliably have gone red against
  the old code. What it refuses is a reintroduced unbounded wait.

---

## T1-remfix.9 · an unexplained transient, recorded rather than smoothed over

One full-suite run in this session reported
`tests/boundaries/test_one_definition_site.py::test_every_source_reading_rule_has_one_definition_site`
failed — `1 failed, 2000 passed` — and the message was lost to a `tail`. The
same node passed alone immediately before and after, and every full run since
has been green. The only mechanism found is that the check `rglob`s and parses
every `.py` under `tests/`, so a file being rewritten underneath it is visible
to it; the runs that *followed* were confirmed contaminated that way (a
background suite racing this session's own edits) and were discarded. The run
recorded as this remediation's evidence was taken with nothing else running.
The transient is written down because M4's T19 had one too and the rule there
was that an unexplained transient is a finding, not a re-run.
