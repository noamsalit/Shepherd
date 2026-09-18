# M1–M4 QA — the fixes, 2026-09-18

Five defects. **D1 and D2 fixed and mutation-proved. D3, D4 and D5 recorded as
design decisions with their reasons.** Every number below was measured on this
tree during this pass.

| what | baseline | after |
|---|---|---|
| default sweep | 1836 passed, 1 skipped, 75 deselected | **1840 passed, 1 skipped, 75 deselected** |
| live lane (`pytest -m live`) | 75 passed | **75 passed, 1841 deselected** |
| `tests/boundaries` | 105 passed | **105 passed** |
| `mypy --strict src` | 126 files clean | **127 files clean** (one new module, below) |
| `wc -l src/shepherd/daemons/controld.py` | 140 | **140** |
| `fleet_summary` at 200 sessions, no card pending | 12 927 B | **12 927 B** |
| `sha256 ~/.claude/settings.json` | `375e5322…d6ac` | **`375e5322…d6ac`** |
| `tmux -L shepherd ls` | `m3`, `master` | **`m3`, `master`, unchanged** |

The file count moved from 126 to 127 because the repair added one module,
`toolsurface/spawn_origin.py`. It is named here rather than left to be noticed:
the exit criterion said 126 and the number that matters is *clean*, but a count
that moved without being declared is the shape this repo refuses.

---

## D1 · CRITICAL · fixed — a master-initiated spawn now reaches the wake set

### The repair: bind `ctx` into the handler call (repair 1)

`types.Handler` becomes `Callable[[ToolArgs, CallerContext], object]` and
`registry._run` calls `tool.handler(args, ctx)`. `invoke()`'s own signature is
**unchanged**, so no file in `web/` or `cli/` moves and Gate A survives — neither
tree defines a handler (measured: `grep -rn "handler=" src/shepherd/cli
src/shepherd/web` hits only `static/vendor/xterm.js`, which is not ours).

**Why not repair 2 (the master passes its own origin as an argument).** It hands
a security-relevant field to the caller, which is exactly what the audience check
exists to prevent: a tier-2 session could then spawn into the master's wake set
by typing a string. The audience is asserted by the consumer's entry point and
the argument mapping is not. That is not a cost worth the smaller diff, and the
smaller diff is the whole of what repair 2 buys.

Both requirements the brief named are asserted, not promised:

* **A caller cannot choose its own origin by argument.**
  `test_a_caller_cannot_choose_its_own_origin_by_argument` reads `spawn_session`'s
  **own schema**, enumerated at test time, asserts no property of it is named for
  the origin, and then drives a call carrying `origin=` and watches `invoke()`
  refuse it.
* **A human's spawn does not wake the master.**
  `test_a_human_spawn_and_a_master_spawn_are_still_different_rows` drives both
  audiences through **one handler with the same argument mapping** — so the only
  difference is the `CallerContext` — and asserts the two origins differ, that
  the human's is not `WAKE_ORIGIN`, and that the wake set holds exactly the
  master's row.

**The signature change is asserted by property, never by a list.**
`test_every_registered_handler_is_handed_the_caller` composes the shipped
`compose_tool_surface`, enumerates `registered_tools()`, and proves each handler
by `inspect.signature(...).bind(args, ctx)` — `bind` is what actually decides
whether `invoke()` can make the call, so `(*args)` and `(args, ctx, extra=1)`
pass for the same reason `invoke()` would. It carries its own control: the same
reader against a one-argument lambda, which must raise. Measured against the
composed registry: **35 tools, 0 refused.** MUT-D1-4 breaks exactly one handler
and the check names it.

### Who asked → which origin

`toolsurface/spawn_origin.py` holds one total map:

| `ActorKind` | `Origin` | why |
|---|---|---|
| `MASTER` | `admission.MASTER_ORIGIN` (`orchestrator`) | D31: master-spawned → the wake set |
| `WORKER` | `queue_worker` | D31 routes a queue-spawned stop to the worker loop, never to the master |
| `HUMAN` | `user_ui` | unchanged; §12's rail is the human's and D31 keeps it there |
| `SESSION` | `user_ui` | **unchanged, and a decision** — see below |

**Keyed on `ActorKind`, not `Audience`, and that is load-bearing.** M5's queue
worker arrives on the `MASTER` audience and is not the master (DP2, K23). Keying
on the audience would have put every worker's session into the master's wake set
the day M5 lands — a defect planted by this repair, invisible until M5. The
derivation is `types.actor_kind_of`, imported, which is already the one
declaration (§T6-4). MUT-D1-3 re-keys it on the audience and the check is red.

**The master's row is `admission.MASTER_ORIGIN`, imported.** That constant and
`reads.WAKE_ORIGIN` were the only two mentions of `Origin.ORCHESTRATOR` in
`src/` and neither was a write. A third spelling here would be a third thing to
keep in step with a value whose whole job is that two modules agree.

**`SESSION` stays at `USER_UI`.** A tier-2 session's spawn is none of §7's five
origins cleanly. Moving it is a spec question about D31's lineage, not a repair,
so this pass moves only the rows D31 names — and the unchanged row is written out
rather than defaulted, so it is as visible as the changed ones.

### Does this satisfy Track C's reversal condition (per-caller scope)?

**Partly, and the honest answer is: it removes the blocker, it does not discharge
the condition.** Track C was cut because `invoke()` checked `ctx.audience` and
then discarded the caller, so nothing below the chokepoint could be scoped to who
was calling. That structural obstacle is **gone**: every handler is now handed
the validated `CallerContext`, which carries `audience`, `caller_id`,
`correlation_id` and `actor_kind`, and `spawn_session` is a worked example of a
handler using it to make a caller-dependent decision.

What is **not** discharged is the rest of Track C's condition. `caller_id` is an
unauthenticated self-stamp exactly as `Audience.HUMAN` is (`policy.py`'s
`CLAIMED_HUMAN` reasoning applies verbatim): `web/server.py:230,299` and
`cli/main.py:164` each construct a context claiming one and nothing proves it. So
per-caller **scope** is now expressible; per-caller **authentication** is not, and
a scope resting on an unauthenticated id is a scope an agent can choose. Whoever
re-opens Track C should read this as *the seam it needed exists; the identity it
needs does not yet*, and should not read the seam as the condition met.

### The proof: a master-initiated spawn reaching the wake set, never a fixture row

`tests/qa/test_s2_spawn_stop_wake.py::test_a_session_the_master_spawned_reaches_the_wake_set`.
It drives `invoke("spawn_session")` as `Audience.MASTER` over the shipped
`register_m3_tools` with a `ScriptedRunner`, stops **that returned id** through
M2's own `handle_stop` over a real captured transcript, and asserts
`wake.peek(store)` is exactly `[session_id]`. `_a_row_that_can_wake` — the fixture
row the old file leaned on — is deliberately not called in it. Both constants are
imported (`SPAWN_ORIGIN_BY_ACTOR`, `WAKE_ORIGIN`), never respelled.

### On the tests/qa scenario this replaced

`test_a_session_the_master_spawned_can_never_reach_the_wake_set` was a
**gap-recorder**, and its own docstring says so: *"if the two are ever made
equal, this test goes red and says so, which is the correct outcome for a check
that exists to record a gap"*, and its failure message says *"the gap this test
records is closed, and S2's chain should be asserted end to end."* That is what
was done. The scenario was not weakened or deleted: it went from asserting an
emptiness to asserting the chain, and S2 gained three checks it did not have
(the human/master split, the argument refusal, the totality of the map). Its
positive control was rewritten the same way — it now asserts a **set equality**
over two routes into one wake set rather than an emptiness beside a twin.

---

## D2 · HIGH · fixed — a pending approval reaches the Needs-You rail

`build_read_tools` / `register_read_tools` grow a **keyword-only, un-defaulted**
`pending_approvals: Callable[[], Sequence[Approval]]`, and
`compose_tool_surface` hands it `approvals.pending` — the same `ApprovalStore`
the gate raises cards on. The store is now built a few lines earlier, before the
read tools register.

**It is a composition, not an import-down.** `tools_m1.py` and `approvals.py` are
both L4, so the question was never layering; it was *which store*. A second
`ApprovalStore` would be a second set of cards, which `M4Wiring`'s own docstring
already refuses. The reader has **no default**: a default of *"no cards"* would
let a composition root forget §12's third source and still be green, which is the
exact defect this parameter repairs. MUT-D2-3 wires an empty reader and is red.

**The row.** §12 draws `1 approval pending · work_item_set_status`, and `rail.js`
renders `titleOf(row) · askOf(row)` — so the mock line *is* `title` and
`needs_you_reason`. `project_pending_approval` fills exactly those, with
`needs_you_reason = card.tool`: the actual ask, never a category. §12 forbids
"session needs attention" and a row saying only "an approval" is the same defect
spelled politely — MUT-D2-2 plants that wording and is red on the rebuilt mock
line.

**One row per card, not an aggregate.** The rail's count is the number of things
a person must answer; an aggregate row reading "1 needs you" over a five-card
backlog is the silence principle 5 refuses. The test asserts
`len(approval_rows) == len(approvals.pending())` — never a literal.

**`rail.js` is byte-unchanged**, so Gate A is untouched. The two row kinds share
**one key set**, derived in the test from `project_needs_you` rather than written
out, so the renderer never has to branch on which kind it was handed; an approval
row is identified by `session_id is None`, a value rather than an omission.

### G-M4-8: this makes it worse, by zero bytes when nothing is pending

`fleet_summary`'s `needs_you` was already the unbounded term and it now grows
with pending cards as well as with blocked sessions. Said out loud in the
function's own docstring, as the brief asked.

**The first cut of this repair cost 950 B and was withdrawn.** It put an
`approval_id` on every row so the `[→]` had a target; at 200 sessions that is 50
rows × one key, and `test_the_master_read_tools_size_does_not_regress` measured
`fleet_summary` at **13 877 B against its 12 927 B baseline** and went red. The
guard was right and the budget was not edited: `rail.js` reads neither id, so the
field was paying 950 B for a consumer that does not exist. It was dropped. The
projection is now **byte-identical to its baseline with no card pending**, and the
added term is bounded by the number of callers parked on the gate at once — far
smaller than the fleet, and the term a person most needs. G-M4-8's bound remains
the open design decision; this repair does not close it and does not enlarge it
in the fleet-size dimension.

### On the tests/qa scenario this replaced

Same shape as D1's, and the same reading.
`test_a_pending_approval_never_reaches_the_needs_you_rail` said *"if the
projection ever grows an approvals term, this goes red and says so, which is the
right outcome for a check that exists to hold a gap open."* It now asserts
arrival: the card is asserted **pending** on the composition's own store first,
then present in the projection, then — after the card is decided — **absent
again**, which the old file could not check at all. The two rail tests that do
not raise a card are untouched.

---

## D3 · HIGH · recorded, not fixed — it needs a transport decision *and* a Gate A re-base nobody may take

Measured again on this tree: `shepherd status` beside a running `controld` exits
1 with *"start the shepherd control daemon"*, byte-identical to the no-daemon
case; `shepherd doctor` succeeds in the same environment.

M1's T18-1 records three options and a recommendation, and I read them before
choosing:

* **(a)** `cli/` reads the loopback API through a small client;
* **(b)** an exporter at the `invoke()` seam that `cli/` consumes like any other
  consumer — the recommendation, on the grounds that (a) is a transport `cli/`
  then has to unlearn;
* **(c)** a read-only `Store` mode — named in the entry itself as the trap,
  because "read-only" is a property of the code path and not of the file.

**All three end at the same wall, and it is not the transport.** Every one of
them requires `cli/` to reach a capability it cannot reach today, which means a
byte changes under `cli/`. Gate A compares `src/shepherd/cli/**` against a frozen
manifest, and its re-base rule permits **exactly one** re-base, by **T24**, which
has already been taken (`rebase.regenerated_by == "T24"`, five `web/` paths
declared, 2026-09-18T09:45:00Z). `test_a_rebase_declares_every_path_whose_digest_moved`
asserts `regenerated_by in (None, "T24")` — so a second re-base is either a red
build or a lie told in a manifest field.

So the honest answer is the one the brief allowed: **it cannot be fixed here.**
It needs (i) the transport decision T18-1 routed to M4 and M4 did not take, and
(ii) an authority to re-base Gate A that this pass does not have and should not
invent. Recommendation unchanged from T18-1: **(b)**. What is new is that the
Gate A cost is now named — whoever takes (b) must take the re-base with it, in
the same pass, with declared paths, and `declared == moved`.

Not attempted, and worth saying: the message cannot be improved either. The text
lives in `cli/commands.py`, which is the frozen tree.

---

## D4 · MEDIUM · recorded — §T25-8 is deterministic, not a race

Confirmed against the shipped code. `tests/daemons/test_shutdown_master.py::
test_no_thread_is_left_blocked_on_an_approval` asserts
`page_answer[0]["is_error"] is True`, and its own `except` writes
`{"is_error": True, "raised": …}` on the raise branch — so the assertion is true
in **both** branches and cannot distinguish them. The ledger's *"can race"* is
generous: measured 20/20, the released foreign worker comes back with
`RuntimeError("store is closed")` and never D54's refusal.

**Recorded here rather than in the ledger**, because the brief says no milestone
ledger is edited in this pass. The correction owed to
`docs/plans/m4-blockers/router-decisions.md` §T25-8 is one word: *can race* →
*deterministically raises on this host*. The three repairs it names (a bounded
grace period, an in-flight-waiter reader, swallowing the exception — the third
being the one this repo refuses) are unchanged, and choosing between the first
two is still a design decision about shutdown ordering.

**The sharper assertion already exists and is not duplicated.**
`tests/qa/test_s7_shutdown_in_flight.py` records the two branches separately and
asserts `branches == {RAISED}` (line 285), with a control proving its own
recorder can produce both. Adding the same property to the shipped M4 test would
make a boundary rule with two implementations — RD-T5-5's defect, which cost this
repo a rule that was red on arrival — so the shipped test is left as it is and
pointed at S7 here instead.

---

## D5 · LOW · recorded, not fixed

* **`shepherd --help` → `unknown command '--help'`, exit 64.** Same wall as D3:
  the parser is `cli/main.py` and Gate A's one re-base is spent. Not fixable
  without the authority D3 needs.
* **`shepherd-sessiond` with no arguments → argparse error, exit 2.** This one
  *is* reachable — the entry point is `shepherd.daemons.sessiond:run`, outside
  Gate A. It was still not changed, and the reason is that the repair is not
  cosmetic: `--expected-schema-version` is required so a relay cannot be started
  against a schema it was not built for, and defaulting it would turn a refusal
  into an assumption. That is a guard, and loosening a guard to improve a console
  script's manners is the trade this repo refuses. The finding stands as written
  — *a defensible design for a supervised unit and a surprise in
  `[project.scripts]`* — and the honest repair is a usage message that says why
  the flag is required, which is a `sessiond` design change, not a QA fix.

---

## The mutation ledger

Technique per RD-T19-7 and CLAUDE.md's mutation section. Every mutation landed in
**`scratchpad/qa-fix/shadow/`** with `src/`, `tests/`, **`docs/`** and
`pyproject.toml` copied, pytest run with `cwd=` the shadow, `__pycache__` cleared
before every run and a sleep past the whole-second boundary (rule 4). **No
mutation is a signal, a `kill`, a subprocess, a socket, a teardown verb or any
reboot-capable call, in any tree** — every row below is a constant, a mapping
row, a dict value or a dropped `extend`. The driver digests live `src/`,
`tests/`, `docs/` and `pyproject.toml` before and after every sweep:
`LIVE src UNTOUCHED: True`, `LIVE tests UNTOUCHED: True`,
`LIVE docs UNTOUCHED: True`, `LIVE pyproject.toml UNTOUCHED: True` on every run.
Driver: `scratchpad/qa-fix/mutate.py`.

Control, unmutated shadow: **15 passed, exit 0.**

**8 mutations: 7 RED, 0 unintended survivors, 1 intended survivor, 1 re-cut.**
Scope is declared per row: each ran against its own scenario's module, the way
MUT-11/12 did in the QA pass.

| id | file | mutation | observed | failing line |
|---|---|---|---|---|
| MUT-D1-1 | `tools_m3.py` | `origin=spawn_origin(ctx)` → `origin=Origin.USER_UI` — D1 restored | **RED** (4 failed) | `the master's spawn did not write the origin the actor map gives it` / `assert <Origin.USER_UI> is <Origin.ORCHESTRATOR>` |
| MUT-D1-2 | `spawn_origin.py` | `ActorKind.HUMAN` → `MASTER_ORIGIN` — a person's spawn wakes the master | **RED** (2 failed) | `a human's spawn and the master's spawn now write the same origin` |
| MUT-D1-3 | `spawn_origin.py` | keyed on `ctx.audience` instead of `actor_kind_of(ctx)` | **RED** (1 failed) | `assert <Origin.ORCHESTRATOR> is <Origin.QUEUE_WORKER>` |
| MUT-D1-4 | `tools_engine.py` | one handler stops taking the caller | **RED** (1 failed) | `these handlers cannot be handed the caller…: ['schema_status: too many positional arguments']` |
| MUT-D1-5 | `registry.py` | `tool.handler(args, ctx)` → `tool.handler(args)` — D1's root constraint | **RED** (6 failed) | `master could not spawn: request failed (correlation_id=s2-turn-1)` |
| MUT-D2-1 | `tools_m1.py` | the approvals `extend` is dropped — D2 restored | **RED** (1 failed) | `the rail's approval rows are not one per pending card` / `assert 0 == 1` |
| MUT-D2-2 | `tools_m1.py` | the ask becomes the category `an approval is waiting` | **RED** (1 failed) | `assert '1 approval pending · an approval is waiting' == '1 approval pending · interrupt_session'` |
| MUT-D2-3 | `compose.py` | the rail is wired to a second, empty set of cards | **RED** (1 failed) | `the rail's approval rows are not one per pending card` |
| **BAD-MUT-1** | `spawn_origin.py` | a comment's backticks become plain text | **SURVIVED, intended** | — the checks read the map, never the prose |

**MUT-D1-4 was re-cut once, and the first cut is recorded because it is the
instructive one.** Its first form was `lambda args, ctx=None:` and it
**survived** — correctly, because a defaulted second parameter still binds two
positional arguments, so nothing about the call changed. That is a **bad
mutation, not a survivor**: it did not express the defect it was aimed at. Re-cut
to a genuine one-argument handler, it is red at the property check that exists
for it. A survivor that turns out to be a bad mutation is the one case where
"SURVIVED" says nothing about the tree, and it is written down rather than
quietly replaced.

---

## Things found false of the defect record, or newly true of the tree

1. **D1's "two occurrences of `Origin.ORCHESTRATOR`, neither a write" was exactly
   right**, and the repair keeps the count honest rather than adding a third: the
   master's row of the new map **imports** `admission.MASTER_ORIGIN` instead of
   respelling the enum member.
2. **The defects file says Gate A survives repair 1 because `invoke()`'s
   signature does not change.** True, and it is true for a second reason worth
   recording: `web/` and `cli/` define **no handler at all**, so even a
   `ToolDef`-level change would not have moved a consumer byte. The grep is in
   the D1 section above.
3. **`tools_m3.py` could not hold the repair.** With the map and its reasoning
   inline the module reached 485 lines against `test_the_three_modules_are_each_
   under_the_cap`'s 450. The cap was **not edited**; the map moved to
   `spawn_origin.py` and that module was **added to the check's own enumeration**
   (four files → five), which is precisely what T23 did for `tools_rename.py` and
   what the check's docstring describes as the honest move. A split that escapes
   the enumeration is a split that hides growth.
4. **D2's first cut regressed a measured budget by 950 B** and was withdrawn
   rather than absorbed. Recorded above under G-M4-8, because a budget guard that
   bites and is then edited is worse than no guard.
5. **Track C's reversal condition is not met by this repair**, only unblocked.
   Recorded in full above, because it is the question a future reader will ask
   and the tempting answer is the wrong one.
