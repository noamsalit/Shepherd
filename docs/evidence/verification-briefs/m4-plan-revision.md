# M4 plan — revision 2 disposition (router)

Two independent reviews. **Both returned blocking findings; one returned CONFIDENCE 0 on security.**
Every finding below that I verified myself is marked **[router-verified]**. Where I have made the
decision, it is made — implement it, do not re-argue it. Where I ask you to decide, decide and say why.

---

## ROUTER DECISION 1 — **Track C is cut from M4.** (T12, T13, T14, T15, and `to_stdio_mcp_server`)

**[router-verified]** `src/shepherd/toolsurface/registry.py:244` is `data = tool.handler(args)`: the
`CallerContext` is consulted for the audience check and then **discarded**. No handler can scope a
call to its caller. And the SESSION audience today already reaches
`send_to_session` (`LOCAL_WRITE`, `tools_messaging.py:218`), `ask_session`, `spawn_session`, and
`get_session_output` (`tools_terminal.py:274`) — I read the audience sets myself.

Mounting that projection into every spawned tier-2 session grants each one an **unscoped
cross-project write API**: `send_to_session(<any id>, text)` types into another project's live agent,
`get_session_output(<any id>)` returns another project's scrollback. §11 says a tier-2 session
*"cannot see other projects"*. §13 says text reaching an agent is untrusted. One prompt-injected
session drives the whole fleet, and the audit log records it faithfully — **attribution, not
authorization**.

Both reviewers arrived at "cut Track C" independently, one on cost and one on security. It is cut.

**This is a deviation from §16, which names two MCP exporters for M4, and it is recorded as one —
not quietly absorbed.** In the plan, write it as a named scope reduction with:
- the security reason above, in full;
- **the prerequisite for ever shipping it**: per-caller scope must exist first — `ctx` bound into the
  call (`tool.handler(args, ctx)` or a per-call closure; neither changes `invoke()`'s signature, so
  Gate A survives) **plus** a property that *every SESSION-audience tool whose schema names a
  session or workspace id refuses an id outside the caller's lineage*, enumerated at test time with
  a negative control;
- `to_stdio_mcp_server` cut **with** it. Shipping a translator nothing calls is M3's T25/F1 defect.
- a new `G-M4-<n>` row, and a line in the plan's own "Differences from agreement".

Also add a **finding about the existing tree, not about M4**: those audience declarations are already
wrong-by-the-spec today. `list_sessions` carries no project scoping for a session caller and
`get_session_output` is not on §11's list at all. Record it as a named gap with an owner, since
nothing could reach it before M4 and nothing will now.

## ROUTER DECISION 2 — the gate and audit sink may not default to absent

**Confirmed by review:** the two injection points are module-level, default to `None`, and `None`
means M1's behaviour — no gate, no audit. `reset_registry()` clears them. `cli/main.py` registers
tools in a process that never composes either. D8 says *"audit log always on at both levels"*; as
designed that is a property of **one composition root**, not of `invoke()`. Worse, clause 2 is
self-sealing: with no gate there is no decision, and "no decision, no record" makes the silence read
as correct.

**Make the absent state impossible.** Take either a lazily-resolved real default sink, or a
`freeze_registry()` that refuses to freeze a registry holding a `local_destructive` tool while the
gate is unset — your choice, argued in the plan. "Existing tests pass unmodified" is a convenience,
and it is not worth a security property. If some residue genuinely cannot be closed inside M4, scope
clause 2 and D8's "always on" **in writing** to the composing process and record the rest as a named
gap with an owner. Note the collision: D38 forbids changing `cli/`, so the obvious repair is barred —
**name that collision in the plan**; it is currently unnamed.

## ROUTER DECISION 3 — `git commit` is not available to you

One reviewer correctly observes that committing the baseline would make
`git diff --stat HEAD -- src/shepherd/web src/shepherd/cli` a strictly stronger Gate A than a
self-generated digest manifest, free. **The user has a standing instruction not to commit**, so this
is not yours or mine to take. Record it in the plan as a **stated, rejected option with the reason**
("stronger, unavailable under a standing instruction; revisit if that changes") so the next reader
does not re-derive it. Keep the manifest, and fix its scope control per finding #9.

---

## Fix these, each in the plan

**The hole — highest priority.** *No task owns the master turn driver.* T23 consumes `send_turn` and
`interrupt_master`; nothing produces them. The component that runs `MasterRuntime.send()`, projects
`MasterEvent`s onto the stream, enforces one-turn-at-a-time, persists `master_session_id`, opens a
turn with the wake summary and stamps `master_last_turn_at` **exists in no task**. Flow A steps 1, 4
and 7 appear in no `Required Checks`. Add the task (an L3 module, no vendor word), with its own
checks, named in the dependency graph and in the Consumes of everything that needs it. A hole like
this gets filled by a builder improvising inside `compose.py`.

**The arithmetic. [router-verified]** `compose_tool_surface` is at `controld.py:76`;
`shutdown, bound = threading.Event(), threading.Event()` is at **line 82** — six lines later. A thread
built inside `compose_tool_surface` cannot receive the Event that `stop()` sets, so the listener never
stops, `shut_down` reports a hung thread on every shutdown, and the socket is never unlinked (M1's
stale-socket failure). Re-derive ADR-M4-6 against the real statement order. *(Track C's cut may
dissolve this entirely — check before rewriting it.)* Also: ADR-M4-6 and T25 **contradict each other**
about whether that edit happens at all, and the first edit site is at line **32**, not 37.

**The unflagged §6 change. [router-verified]** Spec §6:472 is
`def send(self, text: str) -> AsyncIterator[Event]`. The plan writes a synchronous
`Iterator[MasterEvent]` twice while DP8 claims "No §6 shape changes" and DP9 flags only the member
count. **Flag it as a widening beside DP9**, and decide where the event loop lives — a sync `send()`
over an async generator needs a loop thread and a queue that appear in no task, no purity-map row and
no thread budget, and contradict "M4 starts no new thread at boot". Say which thread owns it, when it
is created, when it is torn down, and whether it is in `wiring.threads`. `configure()`'s return-type
change is a second unflagged §6 change.

**The cancellation mechanism.** `anyio.to_thread.run_sync` defaults to `abandon_on_cancel=False`:
cancellation is **deferred until the worker returns**, so the withdrawal path cannot fire until the
600 s approval has already timed out — the exact outcome D54 exists to prevent. Promote DP5's stated
fallback to primary: `interrupt()` withdraws the turn's pending approvals by id through the store,
whose compare-and-set releases the blocked worker immediately. Our code end to end. Set
`abandon_on_cancel=True` as well, and **pin anyio's thread limiter** (default 40) rather than relying
on it. This demotes probe P2 from a hard gate to a confirmation — say so.

**Four anomaly members nothing can increment.** `MASTER_TOOL_UNEXPECTED`,
`MASTER_TOOL_RESULT_ORPHANED`, `MASTER_RESULT_UNMAPPED`, `MASTER_RESUME_LOST` are raised inside
`master/`, which the import allow-list forbids from reaching a counter. That is the plan's *own*
stated defect — "a counter only a process that cannot reach it can increment is always zero" —
reproduced four times across an import boundary. **Inject, don't import**: pass a
`bump: Callable[[AnomalyKind], None]` in from L6. Add the check the table implies: **every M4 anomaly
member has a reachable increment site, enumerated from the enum.**

**Proof defects, all of them the milestone's signature shape:**
- *Gate A has no scope control.* If the enumeration points at nothing, the live set is empty, the
  manifest is empty, they match, and the negative control still passes on its own fixture. Assert the
  live enumeration is **non-empty and contains known paths** before comparing. The plan states this
  rule itself, about a different scan.
- *Clause 6's deciding command is deleted by T24.* At acceptance it exits 4 on a missing path and the
  clause falls back to a transcript — "a test existed" evidence, which the clause preamble forbids.
- *Clause 15 / P-M4-15 is vacuous.* An empty intersection is what you get when `GATE_TOOLS` names a
  tool that is not registered. Assert `GATE_TOOLS ⊆ registered` **above** the disjointness assertion.
- *Clause 16's "no test M1–M3 shipped has been deleted or weakened" has no deciding command.* Freeze
  `pytest --collect-only -q` node ids at step 0b and compare as a subset, with T24's deliberate
  deletion a **named** exception.
- *The flagship approval arrival assertion is a sampling race.* `Thread.is_alive()` after `start()` is
  true whether or not `await_decision` returned. Make arrival a **synchronisation**: the worker sets
  an `Event` *after* the call returns; assert it is **not** set while the card is pending, then decide,
  then assert it is. This is K20's own failure mode inside the test written to enforce K20.
- *`test_every_master_destructive_call_creates_exactly_one` has no owning task* — DP2 names it as one
  of two halves and only the half a do-nothing authorizer satisfies actually ships.
- *The master import allow-list has no dynamic-import fixture.* `importlib.import_module("…")` is a
  call, not an import node. Add a third inert fixture and extend the rule to the call form.
- *Nothing asserts shutdown calls `close()`* or that no thread is left blocked on an approval. Add
  both to T25, arrival-first, through the shipped `shut_down`. Give the approval store a
  `withdraw_all()`.
- *P-M4-2, clause 2 and T6 disagree* about whether "every tool" means the whole registry or one per
  blast class. Pick the implementable one and write it in all three places.
- *T23's byte budget is a number nobody writes down.* A budget invented by the person it constrains is
  not a budget.

**Attribution.** DP2's reading stands — D40's rationale genuinely says the gate exists to bound what
an agent does *on your behalf*, and asking a human to approve their own click is a keystroke prompt in
different clothes. **But the attribution is wrong**: `HUMAN` is an unauthenticated self-stamp any
local process can make, and the record then says *a person approved this*. That is worse than no log,
because it is the artifact the next incident is reconstructed from. Add an `ApprovedBy` member
distinguishing "policy allowed because the caller claimed HUMAN" from "a person pressed Approve".
Also fix `ActorKind.WORKER`, currently unreachable, which makes DP2's promise that an M5 queue worker
gets a card unimplementable — an M5 landmine.

**Correctness and hygiene, lower priority but all real:** T15's prescribed L2→L5 import
(`spawn.py` importing `mcpsrv`) would turn the shipped layer rule red on day one — moot if Track C is
cut, but check; DP2's claim that `decide()` is "the only place audience is consulted" is false of
`registry.py:238`, so scope the sentence; the token-in-argv finding (**`/proc/<pid>/cmdline` is
world-readable on this host, `/proc/<pid>/environ` is not** — verified by the reviewer) is moot with
Track C cut, but if any token ever ships, it goes in the environment or a 0600 file, never argv, and
T15's `test_no_settings_file_is_written` over-reads K3, which forbids writes **under `~/.claude/`**,
not writes anywhere; `get_audit_log` narrowed to `{HUMAN}` is a choice that is neither a DP nor an RD;
DP5's option list omits the non-blocking design, so add it as a **rejected** option with §11 as the
reason; and G1–G6 — the purity map's stale `daemons/tool_rpc.py` row, `RETRY_CAP_REACHED` vs
`WAKE_CAP_REACHED`, T2's five checks called four, **"no two tracks share a file" being false** as the
plan's own table shows (`consumer_manifest.json`, and `tests/e2e/conftest.py` between T22 and T26),
T20's Dependencies omitting T19, and step 0b row 3's grep returning three hits not two.

---

## What both reviewers said not to re-open — leave these alone
DP1's two gates (honest, and set comparisons rather than prose), DP3, DP4, DP7, DP8, DP10, DP11.
P-M4-4 driving the shipped composition rather than a test's own wiring. DP10's "assert the residue
**present**, so the claim cannot be made true by deleting a test" — called the sharpest single idea in
the plan, and I agree. The four probes and their ordering. §17 compliance: clean, checked twice.

## When you are done
Report the revision's task count, the new dependency graph, the acceptance clause count, every
decision you made where I left you the choice, and anything in this disposition you think is wrong —
**say so rather than complying**, the same way a builder is expected to.
