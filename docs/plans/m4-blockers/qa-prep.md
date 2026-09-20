# The QA-prep pass — 2026-09-18

The six items owed before the M1–M4 QA pass. **All six closed.** Every number
below was measured on this tree during this pass, and every rule that changed
what it catches carries a mutation that proves it still catches what it caught
before.

| what | before | after |
|---|---|---|
| default sweep | 1779 passed, 1 skipped, 57 deselected | **1791 passed, 1 skipped, 57 deselected** |
| `tests/boundaries` | 93 passed | **105 passed** |
| `mypy --strict src` | 126 files clean | **126 files clean** |
| live lane (`pytest -m live`) | — | **57 passed, 1792 deselected** |
| `wc -l src/shepherd/daemons/controld.py` | 140 | **140** |
| `len(PENDING_SITES)` | 0 | **0** |
| Gate A / Gate B (`web/`, `cli/` byte-unchanged) | green | **green, and not one byte of `web/` or `cli/` was touched** |
| `sha256 ~/.claude/settings.json` | `375e5322…d6ac` | **`375e5322…d6ac`** |

**Technique, once, for all of it.** Every mutation landed in a per-task shadow
(`scratchpad/qa-prep/shadow/`, with `src/`, `tests/`, **`docs/`** and
`pyproject.toml` copied, pytest run with `cwd=` the shadow) per RD-T19-7. `docs/`
is in the copy set because a dozen shipped tests read probe captures at import
and the remediation lost a whole ledger run to a shadow without it. The live
tree was **never** mutated: the driver digests live `src/` and `tests/` before
and after the whole sweep and prints the comparison (`LIVE SRC UNTOUCHED: True`,
`LIVE TESTS UNTOUCHED: True` on every run below). `__pycache__` is cleared before
every run and each patch sleeps past the second boundary (CLAUDE.md rule 4). No
mutation is a signal, a subprocess, a socket, a teardown verb or a reboot-capable
call, in any tree. Drivers: `scratchpad/qa-prep/{shadow,mutate,rerun_survivors}.py`.

**29 mutations for items 1, 2, 3, 5 and 6: 29 RED, 0 survivors.** Two rows had to
be re-cut and one check had to be strengthened; both are written out below,
because a mutation that was wrong and a mutation that survived are different
facts and only one of them is about the tree.

---

## Item 1 · `module_imports` is blind to call-shaped imports — the bare users are swapped

**What changed.** Four shipped boundary rules and Gate B's reader resolved
imports through `module_imports`, which walks `ast.Import`/`ast.ImportFrom` only.
`importlib.import_module("shepherd.store.db")` and `__import__("sqlite3")` are
`ast.Call` nodes: the module is loaded and reachable exactly as if it had been
imported by statement, and every one of these rules reported it clean.

| rule | file | fixture added |
|---|---|---|
| `storage_violations` (D26) | `test_storage_boundary.py` | `storage_sqlite_outside_store_dynamically.py` — `__import__("sqlite3")`, the spelling that leaves **no import node at all** |
| `consumer_violations` (D19/D35) | `test_consumer_boundary.py` | `consumer_imports_store_dynamically.py` — `importlib.import_module(CONST)` |
| `daemon_import_violations` (ADR-1) | `test_composition_root.py` | `cli_imports_daemons_dynamically.py` — `from importlib import import_module` then a **bare** call |
| `direction_violations` (§5.0) | `test_layer_direction.py` | `signals_imports_toolsurface_dynamically.py` |
| Gate B's `live_imports` (DP1/D38) | `test_consumer_surface_additive.py` | exercised on the consumer fixture; the reader is a **parameter with a default**, and the default is asserted to be `all_imports` |

`module_imports` itself was **not** widened — the bare users were swapped, not the
walker — so `test_master_isolation.py`'s §T7-3 sentinel still holds, and each
swapped rule now carries an assertion that the bare walker is *still* blind to
its own fixture, which is what keeps the rule's premise honest rather than
inherited.

**What the widened rules still catch that they caught before.** Every
statement-form self-check was upgraded from `!= []` to the **whole reported set,
written out** — a non-emptiness assertion cannot tell *"caught the same thing"*
from *"caught something"*, which is the exact mutant that survived T7's first
sweep. So `shepherd.web imports shepherd.store` / `shepherd.store.open_store`,
`shepherd.signals imports sqlite3`, `shepherd.cli imports shepherd.daemons` /
`shepherd.daemons.controld`, and both L2→L4 lines are now literals the rule must
reproduce exactly.

**Mutations (11 rows, all RED).**

| id | mutation | failing line |
|---|---|---|
| MUT-1 | storage rule back to `module_imports` | `assert [] == ['shepherd.signals imports sqlite3']` |
| MUT-2 | consumer rule back to `module_imports` | `assert [] == ['shepherd.web imports shepherd.store.db']` |
| MUT-3 | composition-root rule back to `module_imports` | `assert [] == ['shepherd.cli imports shepherd.daemons.controld']` |
| MUT-4 | layer-direction rule back to `module_imports` | `assert [] == ['shepherd.signals (L2) imports …stream (L4)']` |
| MUT-5 | Gate B's reader back to `module_imports` | `assert <function module_imports> is <function all_imports>` |
| **MUT-6** | **storage rule sees only the call form** (`all_imports - module_imports`) | `assert [] == ['shepherd.signals imports sqlite3']` |
| **MUT-7** | **consumer rule sees only the call form** | `assert [] == ['shepherd.web imports shepherd.store.open_store']` |
| MUT-8 | `__import__("sqlite3")` fixture neutered | `assert [] == ['shepherd.signals imports sqlite3']` |
| MUT-9 | bare-name-call fixture neutered | `assert [] == ['shepherd.cli imports shepherd.daemons.controld']` |
| MUT-10 | upward call-shaped fixture neutered | `assert [] == ['…stream (L4)']` |
| MUT-11 | consumer call-shaped fixture neutered | `assert [] == ['shepherd.web imports shepherd.store.db']` |

**MUT-6 and MUT-7 are the rows that matter**, and they are the ones a widening
pass usually omits: they make the rule see the call form **and nothing else**, so
they fail on the *statement*-form assertions. That is the direction in which a
widening becomes a loosening, and it is red. Both were re-cut once — the first
form named a helper the test module does not import, and `NameError` is a broken
harness, not a behavioural red.

---

## Item 2 · a boundary rule has one definition site, found by property

**Shipped:** `tests/boundaries/test_one_definition_site.py`.

A **boundary rule** is discovered by property, never by a list: a module-level,
non-`test_` function under `tests/` that either inspects source as a tree (it
names `ast.*`, or calls one of the shared walker's scanners) **or** carries a
rule's name (it ends in `_violations`, or it is one of the shared scanners).

The name half is not decoration, and this is the one place the check had to be
strengthened during the pass. **MUT-12 — a second `master_import_violations`
planted in `tests/toolsurface/test_client.py`, the very file §T22-6 named —
SURVIVED the first form of the check**, because the planted copy was a *stub*
(`return []`) and inspected nothing, so a body-only detector walked straight past
it. A stub is exactly how a second implementation arrives: somebody needed the
name to exist in their file. With the name half it is RED, naming both sites.

**§T22-6's convergence, applied.** D19's master predicate — its allow-list, its
floor and `master_import_violations` — moved into `tests/boundaries/_imports.py`,
which is where `logs_importer_violations` already lives for this reason (*"one
function rather than two that can drift apart"*). `test_master_isolation.py`
imports it; `tests/toolsurface/test_client.py`'s inline `permitted`/`forbidden`
block is **gone**, replaced by `master_import_violations(path, package) == []`
over the same scan. The enabling change is one line in `tests/conftest.py`
putting `tests/boundaries` on the path, so the tree's one AST walker is reachable
from every suite — a predicate that lives in one place can only be *used* from
one place if that place is reachable.

That convergence also **strengthened** the client's check: `master_import_violations`
reads `all_imports`, so it sees the two call-shaped spellings the file's own
`imported_names` never could.

### What the property scan found — seven duplicated rules, none of them known

This is the part worth reading, because none of it was in any ledger:

| name | sites | what it is |
|---|---|---|
| `imported_names` | `tests/daemons/test_controld.py`, `tests/daemons/test_controld_composition.py`, `tests/toolsurface/test_client.py` | **three** implementations; the first two return the names an import *binds*, the third returns module paths **and** symbols. One name, two meanings — and `test_controld.py`'s docstring defends the copy in RD-T5-5's own refused words: *"repeated rather than shared"* |
| `imported_modules` | `tests/test_core_types.py`, `tests/toolsurface/test_policy.py` | the **fourth and fifth** implementations of the walker: one resolves relative imports, the other resolves both call-shaped spellings — i.e. a private re-derivation of `module_imports` and of `all_imports` respectively |
| `purity_violations` | `tests/test_core_types.py`, `tests/toolsurface/test_policy.py` | two purity rules, two populations, one name — each resting on its own `imported_modules` |
| `identifiers` | `tests/boundaries/_imports.py`, `tests/web/test_security.py` | one takes a path, one takes an `ast.Module`; a real collision with the shared walker |
| `parsed` | `tests/boundaries/_parse.py`, `tests/signals/test_normalise.py` | the shared cached `ast.parse` and a **hook-payload** parser. Pure name collision, and the next reader of either file has to work out which they are looking at |
| `_string_literals` | `tests/signals/test_normalise.py`, `tests/test_core_runner.py` | both are `string_literals` without its docstring exclusion |
| `scope_violations` | Gate A, Gate B | a shared **idiom** rather than a shared rule; declared deliberately |

All seven are in `DECLARED_SECOND_SITES`, each with its reason and its owner, and
**every declaration is asserted to still be a duplicate** — a converged name
cannot leave a stale exemption behind. They are declared rather than converged in
this pass because converging them changes the population seven shipped checks
measure, which is a change with its own mutation ledger and not a line. The point
of the check is that the *eighth* cannot arrive unnoticed.

One rule is invisible to this check **by design** and is recorded here rather
than absorbed: `tests/test_core_stops.py::test_module_imports_nothing_above_l1…`
inlines its import scan inside the test function. A closure inside a test is that
test's own working, not a rule another file can come to depend on — but it is
also a sixth hand-rolled import scanner, and it is named here so that is a
decision rather than an omission.

**Mutations (5 rows, all RED).**

| id | mutation | failing line |
|---|---|---|
| MUT-12 | a second `master_import_violations`, stubbed, in `test_client.py` | `['tests/boundaries/_imports.py:885', 'tests/toolsurface/test_client.py:37']` |
| MUT-13 | a declared second site withdrawn | `assert ["identifiers is defined 2 times: […test_security.py:42']"] == []` |
| MUT-14 | a declared duplicate converges (rename in `test_security.py`) → the declaration is **stale** | `assert ['identifiers is declared as a second site but has 1'] == []` |
| MUT-15 | a source-reading rule appears in a module the inventory does not name | `assert ['tests/orchestration/test_write_policy.py holds a source-reading rule…'] == []` |
| MUT-16 | the detector reports nothing — the check pointed at nothing | `AssertionError: the scan found only []` |

The check caught its own author once, unprompted: adding
`test_session_audience.py` (item 6) turned it red with *"holds a source-reading
rule and is not in the inventory"* before that module had a single assertion in
it.

---

## Item 3 · `resolved_identifiers` and the bare-name call

**A correction to the ledger first, because it changes where the defect was.**
§T22-3 and the shipped comment in `test_master_isolation.py` both say
*"`identifiers()` collects dotted names, so `open(path)` is invisible to it"*.
**That is false of `identifiers()`** — it collects every `ast.Name` id, and
measured on this tree:

```
'open' in identifiers(core_grows_io.py)          → True
'open' in resolved_identifiers(core_grows_io.py) → False
```

The blindness was `resolved_identifiers`' alone, which is the helper the rule
actually reads. The comment attributed it to the wrong helper, which is why the
fix had been written as a **second, inline `ast.walk`** inside
`core_capability_violations` — one boundary rule with two halves in two shapes,
RD-T5-5's defect in miniature.

**What changed.** `resolved_identifiers` now collects a bare name when, and only
when, it is a **callee** — resolved through `_alias_origins`, so `from os import
fork; fork()` is `os.fork`. A callee is unambiguous in the way a bare attribute
is not: it is the thing being invoked, never a field somebody named, so the
helper's standing guarantee (*a field called `.name` is never mistaken for
`os.name`*) is untouched and is asserted: `read` stays out of the set while
`handle.read` stays in. The inline branch in `core_capability_violations` is
gone.

**What it still catches that it caught before:** `{"os.fork", "socket.socket"} <=
resolved_identifiers(core_grows_io.py)` is asserted **at the helper**, beside the
new `"open"` — because the rule above would report the same three names if the
inline branch had merely moved rather than converged.

**Mutations (2 rows, both RED).**

| id | mutation | failing line |
|---|---|---|
| MUT-17 | the bare-name-call branch dropped from `resolved_identifiers` | `assert ['os.fork', 'socket'] == ['open', 'os.fork', 'socket']` |
| MUT-18 | the positive control loses its bare `open` | `assert ['os.fork', 'socket'] == ['open', 'os.fork', 'socket']` |

**And the fixture rule was widened while we were there.**
`test_the_fixtures_are_inert` enumerated two hand-written tuples; it now binds
**every** planted file in `tests/boundaries/fixtures/` (91 of them), because *"a
planted violation is an inert fixture"* is a claim about all of them and an
enumerated subset is a claim about the ones somebody remembered. Five fixtures
legitimately construct at module scope — the `FoldRule` exclusion rules are about
a *construction site* — and they are in `MODULE_SCOPE_FIXTURES` with their
reasons, compared as a set equality in both directions.

---

## Item 4 · the recorded survivors, re-run with `__pycache__` cleared

**No survivor changed verdict for a cache reason.**

**Which rows are exposed, and why the list is six and not twenty.** A recorded
**RED** proves the mutation took effect, so a stale `.pyc` cannot have produced
one — RD-T6-PYC says so itself. The exposure is to rows whose *final* recorded
verdict is SURVIVED. Rows recorded *"SURVIVED, then RED after the fix"* (T5
MUT-12 and MUT-15, T7 M12, T10 MUT-12, T23 MUT-15/17, T24 MUT-17, T27 MUT-11, the
three `wake.py` rows in the assembled ledger) are **recorded REDs in their final
state** and are not re-run here; that is stated as a reading of the rule rather
than left implied.

| row | recorded | re-run, cache cleared | verdict |
|---|---|---|---|
| T4 BAD-MUT-1 — `pending()` in reverse insertion order | SURVIVED, intended | **SURVIVED** (15 passed) | unchanged |
| T4 BAD-MUT-2 — `WITHDRAWN_TEXT` reworded | SURVIVED, intended | **SURVIVED** (32 passed) | unchanged |
| T16 M10 — the two `from shepherd…` imports swap order | SURVIVED, intended | **SURVIVED** (7 passed) | unchanged |
| T22 BAD-MUT — `and True` on the permitted predicate | SURVIVED, intended | **SURVIVED** (14 passed) | unchanged |
| T24 MUT-15 — `GAP_NOTE` reworded | SURVIVED, intended | **SURVIVED** in T24's own scope | unchanged — see below |
| **T6 MUT-16** — `UNREPORTED_AUTONOMY_LEVEL` `0`→`2` (size-preserving) | SURVIVED first pass, RED once the cache was cleared | **RED**, `assert 2 not in {2, 3}` | the control, and it bites |

T6's MUT-16 is in the table as the **control**: it is the one row known to have
been a false survivor, so if this harness did not clear what it claims to clear,
that row would have come back SURVIVED. It came back RED.

**The one apparent verdict change, isolated.** Run with `tests/boundaries` in the
target set, T24 MUT-15 is RED — but at
`test_consumer_surface_frozen`, *"files changed under web/ or cli/ since the
freeze: ['web/static/chat.js']"*. Re-run at T24's own scope (`tests/web`) it is
**SURVIVED, 145 passed**, exactly as recorded. So the difference is **scope, not
bytecode**, and it carries a fact worth keeping for the QA pass: **Gate A's byte
digest makes any mutation of a `web/` or `cli/` file red regardless of
behaviour**, so a mutation ledger over the consumer trees run against the whole
suite cannot tell a behavioural red from a digest red. T24's narrow scope was the
right one; the ledger did not say the verdict was scope-dependent.

---

## Item 5 · one declaration each, in `toolsurface/types.py`

`SECRET_KEY_MARKERS`, `REDACTED` and `actor_kind_of` now have exactly one
declaration, in `types.py`. `approvals.py`, `audit.py` and `registry.py` import
them.

Both duplications were **forced**, and identically: the clean import would have
dragged `shepherd.logs` into `shepherd status` through `cli/`'s import of
`registry`, and **the shipped DP3 rule checks only *direct* importers, so it
would have passed while being defeated**. `types.py` is stdlib-only, which is why
it can hold all three without re-opening the hole. `mypy --strict src` is clean
over 126 files after the move and no consumer byte changed.

**The guards changed shape, deliberately.** The two drift guards compared two
modules for equality. A drift guard makes a second declaration *safe*; it does
not make it *absent*, and it says nothing at all about a third. They are now:

* **identity**, at the two former holders — `SECRET_KEY_MARKERS is
  audit.SECRET_KEY_MARKERS is types.SECRET_KEY_MARKERS`, and
  `registry.actor_kind_of is audit.actor_kind_of is types.actor_kind_of`. Two
  equal frozensets can be edited apart; `is` cannot.
* **structural**, in `test_one_definition_site.py`:
  `declaring_modules(name) == ["shepherd.toolsurface.types"]`, discovered by
  `modules_defining` (by property, never by filename), which counts **bindings**
  and not imports.

**Mutations (4 rows, all RED).**

| id | mutation | failing line |
|---|---|---|
| MUT-19 | a second `REDACTED` declaration reappears in `audit.py` | `assert ['…audit', '…types'] == ['shepherd.toolsurface.types']` |
| MUT-20 | `registry.py` grows its second actor-kind derivation back | `assert ['…registry', '…types'] == ['shepherd.toolsurface.types']` |
| MUT-21 | **the one declaration loses the `token` marker** | `assert b'ghp_thisisnotarealtokenatall' not in b'{"at": …}'` — the audit encoder, i.e. a reader that is not the module the constant used to live in |
| MUT-22 | the one derivation stops reading the explicit `actor_kind` field | `assert <ActorKind.MASTER> is <ActorKind.WORKER>` |

MUT-21 was re-cut once. Its first form changed the *value* of `REDACTED`
(`<redacted>` → `<hidden>`) and **survived** — correctly: no capture pins that
spelling and every test reads the constant, which is precisely what the single
declaration buys. That is a bad mutation, recorded as one rather than banked (the
shape of T4's BAD-MUT-2). Re-cut to drop a **marker**, it is red in a reader that
is not the declaring module, which is the property that matters: both callers
really read the one list.

---

## Item 6 · clause 14's residue — a registry-wide `SESSION`-audience rule

**Shipped:** `tests/boundaries/test_session_audience.py`, plus the inert fixture
`fixtures/a_new_module_grows_a_session_tool.py`.

**What the tree bound before.** Clause 14's assertion is `session_tools &
MASTER_TOOL_NAMES == set(UNREACHABLE_SESSION_TOOLS)` — an *intersection with the
master tools*. A `SESSION` audience elsewhere was caught **by rule** only on a
destructive M3 tool and **by name** only where some test pins that tool's
audiences with an equality. The remediation measured the residue: a third
`SESSION` audience on `list_subagents`, on `engine_version` or on
`terminal_snapshot` left the **whole default suite green at 1779 passed**.

**Why it is a product problem.** `invoke()` checks `ctx.audience` against the
tool's audiences and then **discards the caller** — `caller_id` reaches the audit
record and never the handler — so no handler can scope a request to its caller.
That is why Track C was cut, and six `SESSION`-audience tools already take an
arbitrary session id. A new tool acquiring that audience unnoticed is the same
hole, one tool wider.

**The rule is structural, and that is a decision.** A registry enumeration can
only see what some composition *registered*; the sentence to enforce is about
**any new tool in a new module**, including one nothing composes yet. So the scan
reads every `ToolDef(...)` construction out of `src/` by AST, resolves `name` and
`audiences` through module-level bindings (`RENAME_TOOL_NAME`, `_EVERY_AUDIENCE`,
`EVERY_AUDIENCE`, `_SESSION_ONLY` are all spellings in this tree), and **refuses
what it cannot resolve** — an audience set spelled a way the rule cannot read is
a *violation*, never a clean answer, which is the only way "every" survives a new
spelling.

**The reviewed set, measured: eight, not two.**

| tool | module | blast class | why |
|---|---|---|---|
| `list_sessions` | `tools_m1.py` | LOCAL_READ | unscoped: the whole fleet |
| `get_session` | `tools_m1.py` | LOCAL_READ | unscoped: **any** id |
| `spawn_session` | `tools_m3.py` | LOCAL_WRITE | unscoped; §12's rail is what bounds it |
| `send_to_session` | `tools_messaging.py` | LOCAL_WRITE | unscoped: writes into any session, including the master's |
| `ask_session` | `tools_messaging.py` | LOCAL_WRITE | unscoped, blocking twin of the above |
| `get_session_output` | `tools_terminal.py` | LOCAL_READ | unscoped; the widest read on the list |
| `report_blocked` | `tools_master.py` | LOCAL_WRITE | G-M4-15: reachable by nothing after the Track C cut |
| `request_help` | `tools_master.py` | LOCAL_WRITE | G-M4-15, with `report_blocked` |

Each entry carries a reason; the six that take an unscoped id say so, asserted as
a **set** and never as a count. Clause 14's `UNREACHABLE_SESSION_TOOLS` is the
last two rows of this table — the shipped check was true and was answering a
narrower question than the clause claimed.

**Mutations (7 rows, all RED).** MUT-23, MUT-24 and MUT-25 reproduce the
remediation's three green rows and are run against the **whole default suite**:

| id | mutation | failing line |
|---|---|---|
| **MUT-23** | a third `SESSION` audience on `terminal_snapshot` (the remediation's S3 row — whole suite was green at 1779) | `{'unreviewed': ['terminal_snapshot'], 'reviewed but gone': []}` |
| **MUT-24** | the same on `engine_version` (S2 row) | `{'unreviewed': ['engine_version'], …}` |
| **MUT-25** | the same on `list_subagents` (S1 row) | `{'unreviewed': ['list_subagents'], …}` |
| MUT-26 | a reviewed entry withdrawn | `{'unreviewed': ['get_session_output'], 'reviewed but gone': ['get_session_output_GONE']}` |
| MUT-27 | an unreadable audience spelling reads as **empty** rather than as a violation | `AssertionError: frozenset()` |
| MUT-28 | an audience set spelled as set arithmetic in a real module | `["tools_messaging.py: ask_session's audiences are spelled in a way this rule cannot read (_EVERY_AUDIENCE \| frozenset())"]` |
| MUT-29 | the positive control loses its `SESSION` audience | the reported set disagrees with the literal |

**The planted tool the brief asked for** is
`fixtures/a_new_module_grows_a_session_tool.py`: a tool called
`snapshot_everything` in a module no shipped rule has heard of, carrying
`{MASTER, SESSION, HUMAN}`, with a second `HUMAN`-only tool beside it so the test
can write out **both** reported sets rather than assert non-emptiness. It is
inert: nothing imports it, and its module body performs no call at all — the
audience sets are set literals rather than `frozenset(...)` calls for exactly
that reason.

---

## Things found false of the tree, or of the ledger

1. **§T22-3's sentence names the wrong helper.** `identifiers()` was never blind
   to a bare `open`; `resolved_identifiers()` was. The shipped comment in
   `test_master_isolation.py` repeated it. Both are corrected in place, with the
   measurement.
2. **There are at least seven duplicated source-reading rules in `tests/`, and
   five hand-rolled re-derivations of the shared walker** (`imported_names` ×3,
   `imported_modules` ×2 — one of which independently re-implements
   `all_imports`, call-shaped spellings and all — plus the inline scan in
   `tests/test_core_stops.py`). RD-T5-5 recorded the defect with three instances;
   the property scan found it is considerably wider than that.
3. **`tests/daemons/test_controld.py`'s `imported_names` docstring defends its
   own duplication** in the words RD-T5-5 refuses: *"the same reader
   `test_controld_composition.py` uses, repeated rather than shared"*. Named
   rather than edited: it is a decision somebody made and wrote down, and
   reversing it is the router's.
4. **Gate A makes every `web/`/`cli/` mutation red by digest**, so a ledger over
   the consumer trees cannot distinguish a behavioural red from a byte red unless
   it is scoped. T24 MUT-15's recorded SURVIVED is correct and scope-dependent,
   and the ledger did not say so.
5. **`oversized_module.py` parses to an empty AST body** (601 comment lines), so
   the widened inertness scan asserts non-empty **source** rather than a non-empty
   body — a fixture whose rule counts lines legitimately has no statements.
6. **A stub defeats a body-based rule detector.** MUT-12 survived the first form
   of item 2's check. Recorded because the lesson generalises: any rule that
   classifies by what code *does* is blind to a copy that does nothing yet.

## Still open after this pass

* **G-M4-8** — §11's *"~40 lines regardless of fleet size"* is violated by
  `fleet_summary()`, the projection its own sentence names, at ten times the
  bound and already over at five sessions. Untouched here: the fix is a design
  decision (a bounded master projection, or an explicitly counted truncation),
  not a number.
* **RD-T5-6** — `test_no_llm_lane_exists` is stricter than the §13 control it
  guards. An M2 rule; unchanged.
* **The seven declared second sites** in `DECLARED_SECOND_SITES`, each with its
  owner. Converging them changes the population seven shipped checks measure.
* **§T25-8** — a worker released at shutdown can race `store.close()`. Unchanged;
  to be observed in QA rather than re-derived.
