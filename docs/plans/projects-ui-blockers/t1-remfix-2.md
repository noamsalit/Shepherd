# T1-remfix-2 — the field that was populated exactly when the kill did not land

Second remediation of Phase 1's delete, 2026-09-22, from `code-reviewer` against
the T1-remfix diff. Scope: `src/shepherd/store/` and `tests/store/` only —
another builder held `toolsurface/` and `web/routes.py` in the main checkout.

Base: `66f8bb4` *"The seventh project verb, and the kill that happens between
the two halves"* (`integration`, fast-forwarded into the worktree).
Commit: `812e375` on `worktree-agent-a77a3c5feee3e88a2`.

The store suite was green throughout the defect's life. Every item below was
**unearned green**, and two of them were green because a test had written the
defect down as the specification.

---

## T1-remfix-2.1 · `killed` was populated exactly when the kill did **not** land · CRITICAL

**Symptom.** `writes.commit_project_delete` reported and gated on the caller's
claim intersected with `fresh.running`:

```python
running = fresh.running
reported = tuple(sid for sid in running if sid in set(killed))
...
survived = tuple(sid for sid in running if sid not in set(killed))
```

`fresh.running` is re-derived **after** the caller went away and killed things,
and `reads.running_sessions_for` defines running as `ended_at IS NULL`
(`reads.py:201,208`). The real kill path is
`store.apply_stop_verdict(...)` (`orchestration/lifecycle.py:135`), which
**writes `ended_at`**. So a session genuinely killed is no longer in `running`
and was filtered **out** of the report; a session only *claimed* killed is still
in `running` and survived the filter. The field said the opposite of what it
meant.

Reproduced by the reviewer's `rev_killed.py`, at `66f8bb4`:

```
=== PROBE A: a kill that actually landed (ended_at set) ===
plan.running = ('s-live',)
deleted   = True
killed    = ()            <-- caller reported ('s-live',)
destroyed = ('s-live',)

=== PROBE B: a kill that did NOT land, reported as landed ===
deleted   = True
killed    = ('s-live',)
destroyed = ('s-live',)
session rows left: 0   (the agent was never stopped)
```

**Two harms from the one line.** The projection hands `killed` straight to the
page (`tools_projects.py:205`), so after stopping four sessions and destroying
their rows the dialog said nothing was killed — on the one verb in this system
that destroys data, and against a docstring promising the opposite. And the
survivor gate `survived = running - killed` made the re-derivation total only
over sessions the caller does **not** claim, so a mistaken or lying caller could
talk the delete's one safety check out of firing.

**Fix — the stronger option, not the smaller one.** Fixing only the report would
have left a destructive verb whose safety check its own caller can argue away.

* The gate is the store's own re-derived running set, **unconditionally**:
  `if plan.on_running is OnRunning.KILL and fresh.running: refuse`.
* The report is the claim intersected with what the store saw **change**
  (`plan.running − fresh.running`), never with what remains.

Both probes after the fix:

```
PROBE A:  deleted = True   killed = ('s-live',)   destroyed = ('s-live',)
PROBE B:  deleted = False  killed = ()            destroyed = ()
          session rows left: 1   (the agent was never stopped)
```

**What the fix does not prove, recorded where it bites.** A session that arrived
*after* the plan was read and was then genuinely killed is **not** reported in
`killed`: it was never in `plan.running`, so the store never observed it running
and cannot prove it stopped rather than having ended on its own. The report
under-reports rather than asserting a stop nobody watched, and `destroyed` still
names the row. The assertion is spelled out in
`test_the_commit_half_refuses_a_session_that_arrived_after_the_kill`, with the
reason, so the next reader does not file it as a bug.

**Remaining dishonesty, stated plainly.** A caller can still make `killed`
*empty* when a kill did land (the latecomer above). A caller can no longer make
`killed` **non-empty** for a session the store did not watch stop, and can no
longer make the delete proceed over a running session at all: the two harms the
review named are closed. The residue is under-reporting, which on a destructive
verb is the safe direction.

**Proof (mutation).** `killed` and the gate were each reverted in turn against a
clean committed tree, `__pycache__` cleared before every run:

| mutation | result |
| --- | --- |
| report intersected with what *remains* (`sid in set(running)`) | RED ×4 — `test_the_commit_half_reports_only_kills_the_store_saw_land`, the matrix, `test_delete_with_kill_stops_them_then_cascades`, `test_a_kill_between_the_two_halves_may_write_to_the_store` |
| gate restored to `running − killed` | RED ×2 — the new test's did-not-land half, and the delegation test's claim-only branch |

---

## T1-remfix-2.2 · `LINEAGE_COLUMNS` was a hand copy of the FK graph · HIGH

**Symptom.** `writes.py:164` is `("parent_session_id", "retry_of")`, introduced
with a comment saying it exists because *"a cascade that knows one and not the
other is exactly the defect this constant exists to close."* Nothing closed the
**third** one: `grep -rn "LINEAGE_COLUMNS" tests/` returned nothing.

The reviewer's `rev_killed.py` probe C2 adds one more `REFERENCES session(id)`
column and the cascade raises

```
RAISED: IntegrityError FOREIGN KEY constraint failed    <-- a verb documented 'Never raises'
```

leaving the project permanently undeletable — the exact defect T1-remfix.2
closed, reopened by a migration. The per-cell `PRAGMA foreign_key_check` cannot
catch it: the transaction aborts before the assertion runs.

**Fix.** `test_lineage_columns_is_every_self_reference_the_schema_declares`
derives the expected set from the **migrated schema** rather than restating it —
the same instinct as this repo's *"pin a constant by parsing the document that
states it"*:

```python
declared = {r["from"] for r in connection.execute("PRAGMA foreign_key_list(session)")
            if r["table"] == "session"}
assert declared == set(writes.LINEAGE_COLUMNS)
```

It also asserts the counts agree, so a duplicated entry cannot pass a set
comparison and sever twice.

**Proof (mutation).** `ALTER TABLE session ADD COLUMN forked_from TEXT REFERENCES
session(id);` appended to `004_projects.sql`:

```
E   AssertionError: assert {'forked_from...', 'retry_of'} == {'parent_sess...', 'retry_of'}
E     Extra items in the left set: 'forked_from'
```

RED, and red *before* the cascade meets it. Fails closed.

---

## T1-remfix-2.3 · the matrix's KILL cells were driven by a kill that cannot happen · MEDIUM

**Symptom.** `plant_session` hardcoded `Ownership.ATTACHED` and never set
`runner_handle` — which is precisely the session the real kill path answers
`no_pane(session_id)` to — and the matrix's kill was `kills_cleanly`, which
returns `True` and touches no row. So every KILL cell of the 36 was driven by
**a claim with no store effect**: the state probe B shows is unsafe and probe A
shows production never produces.

Worse, `tests/store/test_store_delegation.py:694` asserted
`(proceeds.deleted, proceeds.killed) == (True, (latecomer.id,))` for a session
that was **still running**. That test had enshrined the bug as the spec.

**Fix.**

* `plant_session` takes `ownership` and `runner_handle`. A fixture that cannot
  express the session production kills is a fixture whose matrix cannot reach
  the cell that matters — the same argument that added the lineage parameters
  one remediation ago.
* `a_landed_kill(connection)` stops the session through
  `writes.apply_stop_verdict`, writing `ended_at`, the way
  `orchestration/lifecycle.py` does. The matrix uses it, and its running row
  carries a `runner_handle`.
* `kills_cleanly` **survives, named as the negative control** for the
  did-not-land branch, driven by
  `test_the_commit_half_reports_only_kills_the_store_saw_land`. A gate not seen
  to fail is not a gate; each branch says which one it drives.
* The matrix now asserts `outcome.killed` per cell.
* The delegation test changed with the code and says so in its own docstring,
  rather than in the diff: three calls now, refusal (nothing claimed), refusal
  (claimed but not landed), and the control that stops the latecomer first.

---

## T1-remfix-2.4 · the close-race test was a bound, not a window proof · LOW

`test_no_write_hangs_when_close_races_it` races eight writers against `close()`
and its own docstring conceded it *"would not reliably have gone red against the
old code."*

`test_close_cannot_land_between_the_closed_check_and_the_enqueue` constructs the
interleaving instead of hoping for it: it parks a writer **inside** `_queue.put`
(injected, because an unbounded `queue.Queue` never blocks there — which is why
the original probe could not model it) and asserts `close()` **cannot proceed**,
because `_write` holds `_close_lock` across the pair. A control on an idle store
clears the same one-second deadline, so the wait measures the lock and not a
slow `close()`.

It reaches past the public surface deliberately: `_close_lock` is an internal
seam and the invariant is about the internal seam.

**Proof (mutation).** Dedenting `self._queue.put(run)` out of the `with
self._close_lock:` block in `db.py`:

```
E   AssertionError: close() completed while a write was inside _queue.put: the closed-check
E   and the enqueue are not one critical section
```

RED — and under the *same* mutation `test_no_write_hangs_when_close_races_it`
stayed **green**, which is the reviewer's point, measured.

---

## T1-remfix-2.5 · the both-lineage-columns cell was unreachable · LOW

`LINEAGE_SHAPES` was `(None, "parent_session_id", "retry_of")` — exclusive, so
the row that sets *both* columns could not be built. It is the only shape that
exercises `_sever_lineage`'s loop as a loop. Shapes are now tuples of columns,
including `("parent_session_id", "retry_of")`; the matrix is 48 cells.

**Proof (mutation).** A `break` after the first column that matched in
`_sever_lineage`:

```
>   connection.execute("DELETE FROM session WHERE workspace_id = ?", (workspace_id,))
E   sqlite3.IntegrityError: FOREIGN KEY constraint failed
```

RED in the matrix, and it reproduces the original harm exactly: an
`IntegrityError` out of a verb documented *"Never raises"*.

---

## Not done, and why

**`tests/toolsurface/test_tools_projects.py` has two red tests and they are out
of scope.** `test_delete_project_kill_sessions_reports_what_the_kill_actually_did`
and `test_the_kill_runs_outside_the_store_transaction` both fail
`assert answer["deleted"] is True`. They are the *same defect one layer up*: the
`Killer` fake (`test_tools_projects.py:73`) defaults to
`lands = lambda _session_id: True` and writes nothing, so the tool layer's own
tests drive the store with a claim that has no store effect — which the commit
half now correctly refuses.

The fix is the same shape as T1-remfix-2.3: `Killer.lands` must call
`store.apply_stop_verdict` so the kill lands, and
`test_delete_project_keeps_the_project_when_a_kill_does_not_land` already exists
as the negative control. Left to the builder holding `toolsurface/`.

`mypy` reports six pre-existing errors in `tests/store/` (`test_verbs.py:69`,
`test_store_delegation.py:113-116`, `test_stop_verbs.py:17`), all on lines this
remediation did not touch and none about the delete.
