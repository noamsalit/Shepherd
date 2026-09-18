# Router decisions on findings builders raised but did not act on

## RD-T17-3 · `Turn` gains an `ends` field — **approved, owner T18**

T17 measured that the `Turn` shape the plan pins can script only **3 of ADR-M4-5's 7** `MasterEvent`
kinds. `tool_result` and `thinking` are correctly absent (the suite decides what a call did, and
thinking is not ours to fake). But **`error` and `rate_limit` cannot be scripted at all**, which means
the contract suite **cannot ask either implementation what happens on a failed turn or a rate limit** —
and those are precisely the questions a contract suite exists to ask of two implementations.

A seam whose double can only express the happy path produces a suite that proves the happy path and
calls it a contract. **Approved:** `Turn` gains one field, `ends: MasterEventKind = "turn_ended"`,
defaulted so every existing construction in the plan and in §14.2's examples is unchanged. T18 owns
the edit to `testkit/scripted_master.py` for this one field and must then **use** it — a field added
for a question nobody asks is the `to_stdio_mcp_server` defect again.

*This is a deviation from the plan's pinned `Turn`, recorded rather than absorbed.* T17 recommended
it and deliberately did not apply it, which was right: the plan pinned the shape.

## RD-T17-2 · the master seam gains a typed refusal — **approved, owner T18**

The seam has no refusal vocabulary, so `ScriptedMaster` raises a bare `RuntimeError` for "send after
close" and "send past the end of the script". The `Runner` seam one layer down has `RunnerRefusal`,
and every M3 refusal is typed and carries a reason a caller can act on. **A bare `RuntimeError` at a
seam is an untyped refusal, and a suite asserting on its message is asserting on a spelling** — the
defect this milestone has already paid for twice.

**Approved:** `MasterRefusal` in `core/master.py`, the same shape as `RunnerRefusal`. T18 owns that
one addition; `core/master.py`'s member set was pinned by T2's §T2-5, so **T18 must re-pin it in the
same commit** and say so. `ScriptedMaster` raises it; `AgentSDKMaster` (T21) inherits the obligation
through the contract suite.

## RD-T17-11 · builders share a scratchpad path — **fixed here**

T3's mutation driver overwrote T17's scratchpad path mid-run. No result was affected (T17's
mutations had finished), but it is the **third** shared-mutable-state collision today, after the
destroyed ledger entries and the baseline frozen on a moving tree.

**Rule:** a builder's scratch work goes in **`scratchpad/m4-<task>/`** and nowhere else — never a
shared path, never a name another task could pick. Same reasoning as the per-task blocker files: an
instruction to "use the scratchpad" is not a concurrency protocol.

## RD-T11-1 · `tools_list_payload` — **deferred cut, decided before M4 acceptance, owner: router after T20**

T11 shipped `tools_list_payload()` per the plan's Produces block and immediately flagged that **its
only consumer was the tier-2 binding, cut with Tasks 12–15**. That is the same shape the cut itself
names: *shipping a translator nothing calls* (M3's T25/F1, and the reason `to_stdio_mcp_server` went
out with Track C).

**Not cut yet, deliberately.** T20 (`master/sdk_tools.py`) is unbuilt, and if it turns out to need a
wire-shaped payload, cutting now buys a re-add. **The decision is owed the moment T20 lands**: if T20
does not consume it, it is deleted before acceptance and its wire shape is retired *in place* into the
blocker file — the way ADR-M4-4 was kept for whoever builds the binding later, rather than deleted and
re-derived under deadline.

**What must not happen is the third option**: it stays, uncalled, with tests that pass, and M4's
acceptance counts them as evidence. That is M3's uncalled RFC 6455 parser, which cost 14 of 25 tests
in one module before anyone noticed.

## RD-T11-2 · `DENIED_TEXT` has one spelling — **handoff to T4**

`export.py` **declares** the denial text; T4's `build_authorizer` will be the thing that **produces** a
denial. T4 must `import DENIED_TEXT`, never respell it. Two spellings of a user-facing refusal is a
defect nobody notices until the two drift, and no test in either file would see it.

Also from T11, for whoever owns T4: **nothing in this tree can produce a denial today** —
`authorize()` is not behind `invoke()` yet and `Failure` has no denial member — so T11's denial test
proves the *encoder* and says so. T4 closes the other half.

## RD-T27-3 · Flow A step 8's second stamp — **plan corrected, T27 was right**

Flow A step 8 read *"the driver stamps and releases"*. A **second** stamp at turn end marks every stop
that landed **during** the turn as already seen, permanently — the exact lost stop `wake.drain`'s
docstring exists to prevent, and the reason T9 stamps the instant the read *began* rather than when it
finished. T27 stamped once, at open (what clause 19 actually says) and wrote down the discrepancy
instead of implementing the flow as written.

Corrected in place. `test_a_finished_turn_stamps_and_releases_the_slot` asserts the **release** —
asserting a second stamp would have made the bug the specification.

## The "no caller" register — **three mechanisms, none reachable; decide each before acceptance**

M4 is building mechanisms faster than it is building callers. Three are now shipped, tested, and
unreachable from any production path:

| Mechanism | Owner of the gap | What closes it |
|---|---|---|
| D31's retry cap (`link_retry`, `admit(retry=…)`) | §T10-4 | two lines wherever a retry flow lands; no M4 task builds one |
| `tools_list_payload` | §T11-1 / RD-T11-1 | T20 consumes it, or it is cut |
| `MasterRuntime.resume()` — `master_session_id` is persisted and never read back | §T27-6 | two lines in T21 or T25; D10's continuity is half-built without it |

**Each of these is individually defensible and collectively a pattern.** The failure mode is uniform:
a mechanism with passing tests and no caller counts as evidence at acceptance while doing nothing.
M3 shipped exactly this — an RFC 6455 parser `src/` never called, carrying 14 of 25 tests in its
module — and it took a milestone verification to notice.

**Before M4 acceptance each row is wired or recorded as deliberately dormant with the two lines
named.** Neither answer is "leave it and let the tests speak for it".

## RD-T19-7 · mutations of live source must happen in a per-task shadow — **rule change, effective now**

T19 recorded a transient it could not explain: `test_the_prompt_names_no_vendor` failed with
`{'claude'}` while the on-disk source had no such word — `grep -i` clean, `diff` identical, green in
isolation seconds later, green in the next sweep. It wrote it down unexplained rather than explaining
it away, which is why it is actionable.

**The explanation is concurrency, and it is the router's to fix.** Several builders mutated **their own
live source file** and reverted it — permitted by `CLAUDE.md` (the reboot rule forbids planting
violations with effects that escape the process; a prompt-text mutation has none) but *not* safe while
siblings run full sweeps. A sweep that collects during another builder's mutation window sees the
mutant, reports it against a file that is innocent seconds later, and leaves every builder in the tree
doubting a red they cannot reproduce. That is exactly what T19, T27, T11, T17 and T10 each spent time
on today.

**Rule:** a behavioural mutation of live source is applied in a **per-task shadow tree**
(`scratchpad/m4-<task>/shadow/`, `src/` *and* `tests/` copied, pytest run with `cwd=` the shadow) — the
M3 practice — or not at all. The live tree is never mutated, not even briefly, not even with a verified
restore. Restores were all verified today and the damage was still real: it was paid in other
builders' time, not in the tree.

This also removes the last way a clobbered driver can touch `src/`.

## RD-T16-7a · `wake_text()` leaves the client's surface — **approved, correctness, not tidiness**

T16 noticed that `client.wake_text()` and T27's `TurnDriver._opening_text` **both drain**. Two drains is
D31's lost stop: a stop landing between them is stamped as already seen and never wakes anybody. It is
the same defect RD-T27-3 corrected in Flow A step 8, arriving from a second direction within the hour —
which says the drain is easy to call twice and the design should make that impossible rather than
merely avoided.

**Decision: the draining `wake_text` is removed from the client.** The turn driver opens a turn with the
wake summary (clause 19) and is the **single** drain site. If the master later needs to ask what is
waiting *mid-turn*, that is a **`peek`-based** tool in T23 and it must not drain — `peek` exists for
exactly this and T9 built it as the non-stamping twin.

T16 flagged it as "the member most likely to be the one that should go" and left it in place rather
than deciding unilaterally. That was right: removing a pinned `Produces` member is a plan change.

## RD-T16-1 · the client's three extra members — **ratified**

`bind_master_client`, `reset_master_client`, `MasterClientUnbound` are beyond the plan's `Produces`
block. **Ratified**, because the plan's block and the task's own Required Check cannot both be
satisfied by seven plain functions: `autonomy_level` is a `Store` read and the check goes red on the
name `Store`; `wake_text` is L3's and L4→L3 is upward; the two withdrawals live in a module that did
not exist. Injection by the composition root is the only design that satisfies both, and **the
installer is the root's side of the seam — it grants `master/` nothing**, which is what D19 bounds.

T16 wrote out the rejected alternative (`class MasterClient`, two public names instead of ten) and
noted the trade is cheap to reverse while T20 is unwritten. I am not reversing it: the plan pins
module-level defs and the surface is asserted as a **set equality**, so a member added without a test
line is a failing build either way.

## Plan corrections owed (router, not a builder)
- **Task 16's `Consumes` names `ApprovalOutcome`**, which neither pinned signature can return
  (`-> bool`, `-> int`). Importing it would put a name on the client's surface nothing on the surface
  can produce. Stale line; correct it.
- **`docs/plans/m4-blockers/t7.md` does not exist** — T7 finished before the per-task rule and wrote
  into the assembled ledger (§T7-1…§T7-8). Three briefs since have pointed builders at a missing file.
  My error; the content is in `2026-09-17-m4-BLOCKERS.md`.

## The "no caller" register — now five rows
Added: **the client itself** (`bind_master_client` is called from nowhere; two closing lines written out
in §T16-7) and **`wake_text`**, which RD-T16-7a resolves by deletion rather than by wiring. The other
three stand: the retry cap, `tools_list_payload`, `resume()`.

## RD-T5-5 · a boundary rule with three implementations — **owed work, before M1–M4 QA**

T5 found that **DP3's rule existed in three places**. T7 widened one and audited a second — the wrong
one, whose own guard excludes L4 so it never bound the module in question. The third lived in
`tests/logs/test_stop_log.py`, walked `toolsurface/` directly, and was **red on arrival** against the
very file DP3's widening exists to permit. T5 deleted the copy and delegated to T7's single
implementation rather than loosening a second rule — which T7's own docstring forbids by name.

**The general defect: nothing in this tree asserts that a boundary rule has one implementation.** A
rule copied into a second file is a rule that can be widened in one place and keep biting from
another, and the copy is invisible to whoever owns the original. This is `module_imports`' blindness
(§T7-3, fifteen rules) wearing different clothes: both are *"the rule you think you are editing is not
the only one that binds."*

**Owed before the M1–M4 QA pass**, not inside a task: one check asserting each boundary predicate has a
single definition site, found by property. It goes on the QA-prep list with §T7-3's widening.

## RD-T5-6 · `test_no_llm_lane_exists` over-reaches — **owner: router, recorded not fixed**

It bans the literals `api_key`/`apikey` anywhere in `src/`, which is **stricter than the §13 control it
guards**: a *redaction marker list* naming the thing it redacts is exactly what you want, and the rule
reads it as a credential. T5 worked around it by collapsing the markers into the single family name
`key` — defensible on its own merits (one family, one rule, over-matching in the safe direction) and it
recorded the workaround as a workaround rather than presenting it as the design.

Not fixed inside M4: it is an M2 rule, and loosening a credential check to make a milestone fit is the
shape this repo refuses. Recorded with its evidence so the fix is a decision rather than a discovery.

## RD-T4-2 · the approval release path has no working key — **critical, routed to T20 in flight**

T4 shipped `withdraw_all(turn_id)` and found **nothing produces its key.** T27's driver interrupts by a
per-turn ULID; `ApprovalStore.create()` takes no turn id, so `ctx.correlation_id` is the only
structurally available carrier; and T20's pinned `build_sdk_server(tools, caller_id)` has **no
`correlation_id` parameter at all**. Nothing in the plan says what the handler passes.

**Why this is critical rather than untidy.** P2 measured that `interrupt()` does not cancel a running
tool handler — never arrives, and the worker outlives both turn and client. **Withdrawal is therefore
the only mechanism that can free a blocked handler.** A key that matches nothing means every blocked
call rides its full 600 s while ADR-M4-3's release path stays green in every test. The defect class
this milestone keeps paying for, at the one place it costs a user real time.

Messaged to T20 mid-flight with two acceptable answers: carry the turn id and **prove it with a
release that is not a deadline**, or state precisely what parameter is missing and invent nothing. **A
wrong key is worse than an absent one, because it fails silently.**

## RD-T4-4 · M1's `test_no_authorize_call_exists_yet` must be retired by T6, out loud

It is a tripwire that fires when the gate lands inside `invoke()` — which is exactly what T6 does. T6's
Files/Surfaces says *"existing M1 tests must still pass unchanged"*; **both cannot be true.** T4 did not
dodge it: it named its closure `_authorize` (the plan's `Produces` names `build_authorizer`/`describe`,
never `authorize`) and then **proved the tripwire is still armed** with a mutation rather than leaving
the dodge unverified.

**T6 retires it deliberately** — deleted with its reason recorded in the blocker file, never weakened
and never silently dropped. The plan sentence is corrected at the same time.

## RD-T4-3 · §13's redaction rule has two definitions — **owner: router, fix is one line in `types.py`**

T5 declared `SECRET_KEY_MARKERS`/`REDACTED` in `audit.py`; T4 **could not import them**, because
`audit.py` imports `shepherd.logs.jsonl`, the gate sits behind `invoke()`, and `cli/` imports
`registry` — so the import would drag `shepherd.logs` into `shepherd status`. That is the transitive
hole `types.py`'s own docstring refuses, and **the shipped boundary rule only checks direct importers,
so it would have passed while defeating the rule.**

T4 copied the values and added a drift guard comparing the two modules (red on divergence). Correct
under the constraint. **The real fix is one declaration in `types.py`** — T3's file, now free. Folded
into the same pass as RD-T5-5's single-definition check.

## RD-T20-D19 · `core/` is vocabulary, not capability — **D19 widened to an allow-list, by the router**

T20's `sdk_tools.py` imports `shepherd.core.master` (for `ExportedTool`) and `shepherd.core.anomalies`
(for `AnomalyKind`), and T16's test — asserting `master/` imports **only**
`shepherd.toolsurface.client` — went red.

**The strict reading makes the seam unimplementable.** You cannot implement `MasterRuntime` without
importing the Protocol, and you cannot hand a typed member to an injected `bump` without naming the
enum. Three further facts settle it:

1. **`cli/` has done this since M1** — `core.anomalies` and `core.states`, shipped, never flagged, and
   `cli/` is governed by the same decision.
2. **The shipped deny-list already permits it**: T7 measured (§T7-6) that `FORBIDDEN_BELOW_L4` names
   neither `core` nor `host`. T16's test was stricter than both the shipped rule and the design's needs.
3. **`core/` is measurably capability-free** — I checked every module: no I/O, no store, no process, no
   socket. The "socket" hits are a dataclass *field name* and two docstrings; the only machinery is a
   ULID minter with an internal lock.

**Decision: D19 means only-the-client for *capability*; `core/` is vocabulary and is permitted.** The
rule stays an **allow-list**, never a deny-list, so a fourth package cannot arrive unnoticed.

**And the widening carries its own condition.** `core/` being pure is *why* this is safe, so the same
test now asserts it — if a `core/` module ever grows a capability, the rule goes red and the widening
is re-argued rather than silently inherited. That is the difference between widening a rule and
punching a hole in it.

T22 ships the structural allow-list; this is the same property asserted at the place that caught it.

## RD-T11-1 · CLOSED — `tools_list_payload` is cut

T20 answered it by measurement: `create_sdk_mcp_server` builds the `tools/list` entry itself from
`(name, description, input_schema)` and **has no parameter a pre-built payload could fill**; a grep with
T20's files on disk found the function's only references were its own definition and T11's test.

**Cut by the router.** `export.py` carries a retirement note in its place — what the function was, why
it had no consumer, and where the property now lives. T11's test is narrowed to the constant the wire
shape actually turns on (`SCHEMA_WIRE_KEY == "inputSchema"`, still checked against the capture).

**The wire shape got stronger, not weaker.** `tests/master/test_sdk_tools.py::
test_the_schema_and_description_reach_the_wire_unchanged` asserts the **vendor's own `tools/list`
answer** against the literal `{"name", "description", "inputSchema"}` — it reads what the SDK actually
emits, where the retired function only proved what we would have handed it.

Verified after the cut: `tests/toolsurface tests/master tests/boundaries` → 227 passed;
`mypy --strict src` clean over 122 files.

## RD-T20-3 · `MASTER_TOOL_UNEXPECTED` belongs to T21 — **ratified**

The plan contradicts itself: its anomaly table and `PENDING_SITES` assign the member to T20, while
**Task 21's own body** says `can_use_tool=self._belt` and *"the belt denies, counts
`MASTER_TOOL_UNEXPECTED` through an injected `bump`"* — and T20's Allowed Scope is "nothing else, and
in particular no policy".

T20 **re-pointed the row to T21 rather than removing it**, which is the right move: the belt is
unreachable from anything `sdk_tools.py` builds (an in-process MCP server dispatches by registered name;
P3 showed the belt fires on the *client's* `allowed_tools`), so putting the site there would have meant
a helper with no caller until T21 wrote one — the "no caller" register's exact failure mode, created
deliberately.

**Ratified: T21 owns it**, and the self-expiring row now names T21 so the check enforces it.

## RD-T6-PYC · stale bytecode can record a false survivor — **rule added to `CLAUDE.md`**

T6's MUT-16 first reported **SURVIVED**. It was the only **size-preserving** mutation in its ledger (a
single digit). CPython's freshness check is `(source mtime in whole seconds, source size)`, so a
same-size edit landing in the same second as the last compile re-imports the **unmutated** bytecode.
Applied alone, it was red.

**Why this matters more than one row:** a false survivor is a hole in the tree *written down as proof
there isn't one* — the exact inversion of what a mutation ledger is for. It is also the best
explanation for T19's §T19-7 transient, where a test failed naming a word that was not in the file on
disk, green in isolation seconds later: a mutant `.pyc` looks exactly like that from outside.

**Measured exposure:** 7 of M4's 9 mutation drivers do not clear `__pycache__` (only T6's and T21's
do). **Recorded REDs are unaffected** — a red proves the mutation took effect. The exposure is to
**survivors**, and every unintended survivor this milestone recorded was chased down and closed as a
real test gap (T5's two, T27's tautology, T10's thread-ident, T7's `!= []`, T16's control). So the
evidence base is believed sound, and that belief is now **stated with its basis rather than assumed**.

**Added to `CLAUDE.md`'s mutation section as rule 4**, and to the QA-prep list: re-run the milestone's
recorded survivors with the cache cleared, so "believed sound" becomes "checked".

## RD-T16-7a · APPLIED — and it was recorded as done while the code still had it

T21 found that `wake_text()` was **still in `toolsurface/client.py`** and still on the surface
equality, an hour after I recorded the decision to remove it. **My error**: a decision written into
this file is not a decision executed, and nothing in the process noticed the gap — the register said
"resolved by deletion" and the deletion had not happened.

Now actually done: the public function is replaced by a retirement note carrying the correctness
reason (two drains is D31's lost stop), the wiring field and its parameter are gone, and four test
sites are cleaned. `bind_master_client` takes **three** callables, not four. One consumer in T20's
tests needed the same cleanup and got it.

**The process lesson, since this is the second thing of its shape today:** a router decision that
changes code needs the change made in the same pass that records it, or it needs an owner and a
deadline like every other open row. "Recorded" and "done" are different states and the register did
not distinguish them. From here the register marks each row **DECIDED** or **APPLIED**, never both by
implication.

Verified after: `tests/toolsurface tests/master tests/boundaries` → 257 passed.

## G-M4-8 · CONFIRMED BY MEASUREMENT — `fleet_tree` is 139 KB at 200 sessions, and the master can call it

**DECIDED, not yet APPLIED.** T23 took the measurement step 0b row 9 never took (T1 correctly refused
to invent it — building a fixture fleet is code, outside a probe's scope):

| projection | 200 sessions, 8 workspaces, a quarter `needs_you` |
|---|---|
| `fleet_summary` | **12 927 B** |
| `fleet_tree` | **139 323 B** — roughly **35 000 tokens** |

Byte-identical across two runs. §11 promises *"~40 lines regardless of fleet size."* That is false of
this tree by two orders of magnitude at the top end.

**Why it is a product problem and not a note.** I checked the audience myself:
`fleet_tree` and `fleet_summary` are both `LOCAL_READ` with audiences `{HUMAN, MASTER}`. So **the
orchestrator can call a 35 000-token tool**, and M4 is the milestone that gives it the ability to.
One call could consume a large fraction of the master's context on fleet state alone — for a tool
whose entire purpose is a glance.

**Not fixed inside M4, and the reason is the one T23 gave for not editing the budget:** these are
**M1 projections** that no M4 task lists in Files/Surfaces, and the fix is a design decision (page it,
cap it, or give the master a narrower projection than the human's) rather than a number to adjust.
T23 recorded it as a blocker and changed nothing in `tools_m1.py`, which was right.

**Owed before the M1–M4 QA pass, with the options named:**
1. give `MASTER` a bounded projection and leave the human's unbounded (the human reads a page, the
   model reads a context window — they were never the same requirement);
2. cap `fleet_tree` with an explicit, counted truncation (principle 5: the unknown is displayed, so
   *"showing 40 of 213"* is a fact, not a silence);
3. drop `MASTER` from `fleet_tree`'s audiences and let the master use `fleet_summary`.

My reading is (1) or (3); (2) alone leaves the master choosing how much of its own context to burn.
**This goes to the milestone verifier as a named clause-level finding**, because a verifier scoring
§11's "~40 lines" against this tree would be scoring a sentence the tree does not honour.

## The QA-prep list — owed before the M1–M4 QA pass, none of it inside a task

Four items, and **three are the same defect wearing different clothes**: *the rule you think you are
editing is not the only thing that binds, and the helper it rests on does not see every spelling.*

1. **§T7-3 — `module_imports` is blind to call-shaped imports**, and **fifteen shipped rules use it
   bare**. `importlib.import_module("x")` returns `['importlib']`. T7 built widened helpers and
   deliberately did not swap them under live builders; T22's rule uses them.
2. **RD-T5-5 — a boundary rule can have several implementations.** DP3's had **three**; one was red on
   arrival against the module the widening exists to permit. D19's master predicate now has **two**
   (T21's inline check and T22's `master_import_violations`) — they agree exactly, and the
   **duplication** is the defect, not either copy. One-line convergence named in §T22-6.
3. **T22's new finding, the fourth instance** — `identifiers()`/`resolved_identifiers()` collect
   **dotted names only**, so a bare-name builtin call like `open(path)` is invisible to them. Same
   blindness as `module_imports`, one AST node class over. T22 shipped `core_grows_io.py` as the
   positive control precisely because **no module in the shipped tree spells bare `open`**.
4. **RD-T6-PYC — re-run the milestone's recorded survivors with `__pycache__` cleared**, so "believed
   sound" becomes "checked".

Plus two one-line repairs whose home is `types.py`: the duplicated redaction constants (RD-T4-3) and
the duplicated `actor_kind_of` (§T6-4) — both forced by a transitive-import constraint the shipped
rule cannot see, both currently held by drift guards.

**Why this is a list and not a task:** every item is about M1–M3 code that M4 merely *surfaced*, and
each fix touches a suite several builders depend on. They go in one quiet pass before QA, so QA finds
product defects rather than re-finding these.

## §T25-8 · a worker released at shutdown can race `store.close()` — **DECIDED: record, do not fix inside M4**

T25 found it via clause 20's second caller. A worker freed by shutdown's withdrawal still has to count
`APPROVAL_WITHDRAWN`; `shut_down` closes the store as soon as the three threads **it owns** have
joined, and a released worker that is not one of them can come back to `RuntimeError("store is
closed")`. **Real in production** — `ThreadingHTTPServer` serves off threads that are not in
`Controld.threads`.

**Clause 20's promise still holds and is asserted**: nobody is left *blocked*. What can happen is that
a released caller raises instead of returning D54's refusal. T25's test records the release moment and
the outcome — answer **or** raise — rather than laundering the second into the first, which is the
honest shape.

**Not fixed in M4, deliberately.** The three repairs are a bounded grace period, an in-flight-waiter
reader on `ApprovalStore`, or swallowing the exception — and the third is the one this repo refuses.
Choosing between the first two is a design decision about shutdown ordering, not a line. It goes to
the milestone verifier as a named gap with its three options, and to the QA pass as something to
observe rather than re-derive.

## T8-3 row 7 · re-recorded OPEN, and the plan's one-line estimate was wrong

The plan routed it here as *"one line at `compose.py`"*. T25 measured: `make_run_argv(permitted,
commands)` has **no `prefix` parameter** (`runner/local.py:191`), so closing it is a signature change
**plus** a new refusal rule **plus** an edit to `T8_3_TABLE`'s asserted OPEN count — three files and a
design decision. Re-recorded OPEN with the real cost, which is what the plan's own rule permits.

## G-M4-8 · CORRECTED by the M4 verifier — I attributed the spec's bound to the wrong projection

My write-up said §11's *"~40 lines regardless of fleet size"* was about `fleet_tree`. **It is about
`fleet_summary()`** — spec lines 560 and 1863 both name it, and I have read both. The verifier caught
it and measured the projection the sentence actually governs:

| fleet | `fleet_summary` | pretty-printed lines | `fleet_tree` |
|---|---|---|---|
| 5 | 1 924 B | **92** | 3 943 B |
| 25 | 3 071 B | **127** | 18 037 B |
| 200 | 12 927 B | **428** | 139 323 B |

So §11's promise is violated **by the projection it names**, at ten times the bound, and it is already
over **at five sessions** — `anomalies` alone is a 38-key dict. The growth term is `needs_you`, an
unbounded list: 2 entries at fleet 5, **50** at fleet 200.

**The consequence is that one of my three remediation options does not work.** Option 3 — *"drop
`MASTER` from `fleet_tree`'s audiences and let the master use `fleet_summary`"* — moves the master from
~35k tokens to ~3.2k tokens and **428 lines**, still linear in fleet size. It does not restore the
promise; it makes the violation smaller. **Options 1 and 2 are the only two that address the sentence**
(a bounded master projection, or an explicitly counted truncation), and my reading is option 1 — the
human reads a page, the model reads a context window, and those were never the same requirement.

**The lesson is mine.** I wrote a finding from a builder's report and cited a spec sentence without
opening it, and the error survived into three remediation options and a verifier brief. *Check the
shape before building on it* is the repo's first rule about data; it applies to specs too.
