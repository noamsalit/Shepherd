# Remediation of M4's milestone verification — 2026-09-18

Verification returned **FAIL: 20 PASS / 1 FAIL** over 21 clauses, plus three clauses whose cited
evidence did not decide them. **No product code was implicated and none was changed.** One check was
missing; five sentences were wrong. Every number below was measured on this tree during this pass.

| what | before | after |
|---|---|---|
| `.venv/bin/pytest tests/boundaries/test_collected_node_ids.py` | exit **4**, *"no tests ran"* — the file did not exist | exit **0**, 7 passed |
| `tests/boundaries/collected_node_ids.txt` (1480 node ids) | read by nothing | read by the check; **never regenerated** |
| default sweep | 1772 passed, 1 skipped, 57 deselected | **1779 passed, 1 skipped, 57 deselected** (the 7 new ones are this check's) |
| `mypy --strict src` | — | **Success: no issues found in 126 source files** |
| `tests/boundaries` | — | **93 passed** |
| `wc -l src/shepherd/daemons/controld.py` | 140 | **140**, both guard constants on three unedited lines |
| `len(PENDING_SITES)` | — | **0** |

---

## R-1 · Clause 16's deciding command exists, and the clause's promise was false

**The defect, stated as the verification stated it.** At revision 1 clause 16's sentence *"no test
M1–M3 shipped has been deleted or weakened"* had **no command at all**. Revision 2 gave it one — and
the command named `tests/boundaries/test_collected_node_ids.py`, **a file no task ever built**. So
the sentence still had no way to fail, and the 1480-node-id baseline frozen at step 0b row 10 was
read by nothing. That is *recorded ≠ applied* for the third time in this milestone (RD-T16-7a's own
note says the register must mark rows **DECIDED** or **APPLIED**, never both by implication).

**And the property was false as written.** Clause 16 promised *"a named exception list that is
expected to be empty"* and named T24 as the only task permitted a removal. Measured:

```
comm -23 <(grep '::' tests/boundaries/collected_node_ids.txt | sort) \
         <(.venv/bin/pytest --collect-only -q -o addopts='-m "not live"' | grep '::' | sort)
→ tests/toolsurface/test_registry.py::test_no_authorize_call_exists_yet      (exactly one line)
```

The removal is **legitimate and documented**: M1's tripwire, which fires precisely when the gate
lands inside `invoke()`. Retired deliberately by T6 with its reason recorded and its replacement
named — **RD-T4-4**, applied at `t6.md` §T6-1. Revision 2 reasoned about the right property and the
wrong task: T24 does indeed remove nothing.

### What was built

`tests/boundaries/test_collected_node_ids.py` — one module, seven tests, no product code touched.

* `live_node_ids()` re-runs step 0b row 10's **corrected** command in a subprocess
  (`--collect-only -q -o addopts='-m "not live"'`; `addopts` already carries `-q`, and a second one
  makes it `-qq`, which prints per-file counts rather than node ids — T1-1, the third time that
  doubling cost something).
* `subset_violations(baseline, live, retired)` is a **pure predicate** returning a list of readable
  violations, so each of its failure paths can be driven directly instead of shipping untested
  (the shape `scope_violations` uses in Gate A).
* `RETIRED_NODE_IDS` is a **named, non-empty exception list of exactly one entry**, each carrying
  its reason and the decision that authorised it, asserted to carry both.

### Mutation ledger — 6 applied, 6 red, 0 survivors

Technique per **RD-T19-7**: every mutation applied to a per-task shadow tree
(`scratchpad/m4-remfix/shadow/`, `src/` + `tests/` + `docs/` + `pyproject.toml` copied, pytest run
with `cwd=` the shadow). **The live tree was never mutated, not once, not briefly.** Every mutation
is pure text in test-side predicate code or a data file — no signal, no subprocess, no socket
(CLAUDE.md mutation rules 1–3). **`__pycache__` cleared before every run** (rule 4); the restore is
asserted, not assumed; the shadow is deleted afterwards. Driver:
`scratchpad/m4-remfix/mutate.py`.

| id | mutation | verdict | what caught it |
|---|---|---|---|
| MUT-1 | the stale-exemption guard removed | **RED** | `test_a_stale_exemption_is_caught` |
| MUT-2 | the empty/`-qq` parse guard removed | **RED** | `test_an_empty_baseline_is_not_a_passing_compare`; `test_a_doubled_q_transcript_cannot_pass_as_a_collection` |
| MUT-3 | the missing-node-id guard removed | **RED** | `test_a_second_deletion_is_caught` |
| MUT-4 | the unreadable-baseline guard removed | **RED** | `test_an_unreadable_baseline_is_not_a_passing_compare` |
| MUT-5 | **a shipped test deleted from the tree** (`test_registration_rejects_schema_without_type` renamed out of collection) | **RED** | `test_every_node_id_frozen_at_step_0b_still_collects`, naming the node id |
| MUT-6 | **the baseline file emptied on disk** | **RED** | `test_every_node_id_frozen_at_step_0b_still_collects` and two others |

Control green before the ledger and after every restore (`7 passed`). The three traps the brief
named — empty/unreadable baseline, stale exemption, a second deletion — are MUT-2/MUT-6, MUT-1, and
MUT-3/MUT-5 respectively, each proved from **both** directions: the guard removed, and the real
event staged.

**One harness defect found and fixed, and it is worth recording.** The first ledger run reported a
control that was *not* green — `4 passed, 3 errors` — and every row still said RED. The errors were
the shadow's own: `docs/` was not copied, and a dozen shipped tests read capture files under
`docs/probes/` at import time, so the inner collection exited 2 and `live_node_ids()` refused. Every
"RED" in that run was a **false red from a broken harness**. *When a result surprises you, suspect
the observation method before the system* — the row was not banked; `docs/` was added to the copy set
and the whole ledger re-run.

**The baseline file was read, never regenerated.** Regenerating it destroys the property.

---

## R-2 · Clause 14 — the cited evidence does not decide the sentence, **and the wider property is weaker than the verification recorded**

Clause 14 said the `SESSION`-audience tool names **equal** a written-out set, *"so a third one
appearing is a failing build."* The shipped assertion is

```python
session_tools & MASTER_TOOL_NAMES == set(UNREACHABLE_SESSION_TOOLS)   # test_tools_master.py:291
```

— an **intersection with the master tools**, so a `SESSION` audience anywhere else is invisible to
it. The verification proved the clause's own command stays green (40 passed) with a third
`SESSION`-audience tool present, and reported that the build still fails via
`tests/toolsurface/test_tools_m3.py`.

**Measured here, in a shadow tree, one tool per row, whole default suite each time:**

| a third `SESSION`-audience tool | clause 14's command | the whole default suite |
|---|---|---|
| `list_subagents` (`tools_m1.py:456`) | green | **green — 1779 passed** |
| `engine_version` (`tools_engine.py:92`) | green | **green** |
| terminal `snapshot` (`tools_terminal.py:298`) | green | **green** |
| `rename_session` (`tools_rename.py:151`) | green | red — `test_rename_session_is_registered_by_this_task_…`, `test_a_tier_two_session_cannot_rename_anything` |
| `interrupt_session` (`tools_m3.py:367`, destructive) | green | red — `test_every_m3_tool_declares_a_blast_class_and_audiences` |

The S1 row was re-run with the mutation **proved present on disk** before the suite ran, because a
survivor is the result most worth doubting (RD-T6-PYC).

**So the verification's statement is true only of the tool it happened to pick.** The tree catches a
`SESSION` audience on a `local_destructive` M3 tool **by rule**, and on a handful of tools **by
name** where a test pins the audiences with an equality. On any other tool — and on a new tool in a
new module — a third `SESSION` audience is caught by **nothing**.

**Plan corrected** (wording, not tests, per the brief): the clause now claims the `SESSION`-audience
names **among the master tools**, cites the assertion by node id, adds the commands that decide the
pinned half, and records the residue as a gap rather than claiming it closed. It is the same defect
class as G-M4-15/16: a capability nobody can reach and nobody noticed.

---

## R-3 · Clause 20 cited a file with no shutdown test

`tests/toolsurface/test_compose_m4.py` contains **no** occurrence of `shutdown` or `shut_down`
(`grep -n` returns nothing). The property — *shutdown closes the master and leaves nothing blocked* —
is proved by `tests/daemons/test_shutdown_master.py`, which is where the close-and-withdraw step
lives (`daemons/shutdown.py`, ADR-M4-6). Measured: `.venv/bin/pytest tests/daemons/test_shutdown_master.py`
→ **4 passed**, exit 0. Path substituted in the clause; `wc -l src/shepherd/daemons/controld.py` (140)
is unchanged as the second deciding command.

---

## R-4 · Clause 21 counted docstring lines, not the table

`grep -c '^    "' tests/test_core_master.py` returns **36** against a `PENDING_SITES` that is
genuinely **empty** — it counts every four-space-indented quoted line in a 500-line file, most of
them prose. A count that is wrong about the state the clause asserts is not a measurement of it.
Replaced with a measurement that reads the table:

```
.venv/bin/python -c "import sys; sys.path[:0] = ['tests', 'src']; from test_core_master import PENDING_SITES; print(len(PENDING_SITES)); raise SystemExit(1 if PENDING_SITES else 0)"
→ 0        exit 0
```

It prints the count and **exits non-zero while the table is non-empty**, which is what "M4 is not
done while it is non-empty" needs.

---

## R-5 · Clause 18 named one socket family, and not the one the lane uses

`shepherd-m4-t26` (`tests/e2e/test_live_master.py:148`) is written into `app_state` as a runner
socket name; the live lane's actual tmux server is created on **`shepherd-m3-live`**
(`tests/e2e/conftest.py::LIVE_TMUX_SOCKET`). A clause that checks only `shepherd-m4-*` goes vacuous
the moment that constant is retired, while tmux work continues elsewhere. Both are now named. The
socket is the invariant; session names are read, never written, never hard-coded (CLAUDE.md).

---

## R-6 · T6 §T6-8.1's correction, applied

Task 6's *Files/Surfaces* line read *"existing M1 tests must still pass unchanged"*. RD-T4-4 recorded
that the sentence and the tripwire cannot both be honoured, and T6 §T6-8.1 wrote the correction —
which was never applied to the plan. Applied now, in place, with both exceptions T6 named (the
retired tripwire, and the tests that must compose a chokepoint under fail-closed).

---

## R-7 · G-M4-8, re-measured rather than inherited

§11's *"~40 lines regardless of fleet size"* is about **`fleet_summary()`** —
`docs/specs/orchestrator-platform.md:560` and `:1863`, both opened and read here. Re-measured with
T23's own `seed_fleet` fixture builder (`scratchpad/m4-remfix/measure_g_m4_8.py`):

| fleet | `fleet_summary` | pretty-printed lines | `needs_you` rows | `fleet_tree` |
|---|---|---|---|---|
| 5 | 1 924 B | **92** | 2 | 3 943 B |
| 25 | 3 071 B | **127** | 7 | 18 037 B |
| 200 | 12 927 B | **428** | 50 | 139 323 B |

Byte-identical to the router's corrected table, reproduced independently. The promise is violated by
the projection its own sentence names, at ten times the bound, and it is already over **at five
sessions**; the growth term is the unbounded `needs_you` list. Recorded in the plan's Progress notes
with the consequence that follows from it: option 3 (*drop `MASTER` from `fleet_tree`'s audiences*)
does not restore the promise, it only makes the violation smaller — a bounded master projection or
an explicitly counted truncation are the two options that address the sentence.

---

## Still open after this pass

1. **Clause 14's residue** (R-2): a `SESSION` audience on an unpinned tool, or on a new tool in a new
   module, is caught by nothing. A registry-wide rule — *"the `SESSION`-audience set over the whole
   registry equals this set"* — is the one-line closure, and it is a **test change**, which this pass
   was scoped out of.
2. **G-M4-8** (R-7) stays open with its two viable options, as the QA-prep list already records.
3. The QA-prep list's four items and the two `types.py` one-line repairs are untouched by this pass.

## Files this pass touched

* `tests/boundaries/test_collected_node_ids.py` — **new**
* `docs/plans/2026-09-17-m4-orchestrator-plan.md` — acceptance clauses 14, 16, 18, 20, 21; Task 6's
  Files/Surfaces line (§T6-8.1); Progress notes. Nothing else.
* `docs/plans/m4-blockers/remediation.md` — this file
* `scratchpad/m4-remfix/` — the drivers (`mutate.py`, `clause14.py`, `clause14b.py`, `clause14c.py`,
  `measure_g_m4_8.py`); shadow trees created and deleted within each run

`tests/boundaries/collected_node_ids.txt` was **read, never regenerated**.
