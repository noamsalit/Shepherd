# Patterns

## User Standards

- **The spec's decision log (§3) is law.** 65 numbered decisions (D1–D65, plus D38.1) with reasoning. Do not silently
  reverse one — if implementation pressure pushes against a decision, say so and re-decide out loud.
- **Typed, strict, small** (spec principle 6): Python 3.12, `mypy --strict`, no `Any`. Single
  responsibility per module; a file past ~600 lines is a signal it is doing too much.
- **Nothing we install may harm Claude Code** (principle 4): hooks time out, swallow all
  exceptions, always exit 0. A dead daemon degrades visibility, never agents.
- **Unknown is a first-class value** (principle 5), counted and displayed — never hidden.
- **One direction, one store** (principle 1): no consumer gets a private read path into engine state.
- **`store/` exposes domain verbs returning dataclasses** (D33). No caller passes SQL, receives a
  driver row, or opens a transaction.
- **No `shell=True` anywhere** (§13). argv lists only.
- **Naming.** The product is `shepherd`. The consumer-facing word for a `workspace` row is
  **project** (D22). The 2026-09-21 redesign renames three UI labels and nothing else: the fleet
  page becomes the **Flock**, `unfinished` prints as **stranded**, `paused` as **limit exceeded**,
  `unclassified` as **unknown**. Bucket values in code are unchanged, and `core.stops.PALETTE`
  still carries the old labels — see `docs/design/ui-decisions.md` before touching either.

## Common Gotchas

- **Hook events are documented, not guaranteed.** Half the events the spec subscribes to were
  never observed firing. Ingest must be field-tolerant: an absent field degrades its column to
  null and the UI hides that chip. Never key logic off a field's mere presence.
- **`Stop` has no `stop_reason` field.** The spec's §8 completeness split is gated on
  `Stop.stop_reason = end_turn`, which does not exist in the real payload.
- **`claude` transcripts are append-only JSONL and a daemon killed mid-write leaves a malformed
  trailing line.** Every reader must skip malformed trailing lines (D25).
- **No node/npm on this host.** The frontend must be plain ES modules served as-is; there is no
  `tsc` to compile the "vanilla TypeScript" the spec's stack section names.
- **`~/.claude/projects/<slug>/` uses a path-slug, not the session id** — transcript location is
  derived from `cwd`, so `locate_transcript` cannot assume a flat layout.

- **Never run `tmux kill-server` or touch the default tmux server.** This Claude Code session runs inside
  tmux; a spike's `tmux kill-server` killed this session, a background planner, and the user's other tmux
  sessions (2026-09-12). All spikes and Shepherd's `LocalRunner` itself must use a private socket
  (`tmux -L <name>`) and target only sessions they created.
- **tmux session names cannot safely contain `:` or `.`** (target syntax uses them as separators). Spec §9's
  `shepherd:<session_id>` naming must be verified in the tmux spike before M3.


### Checks that report success without checking (M1 batch 1, 2026-09-16 — all found live, all proven)

These are the defect class that dominated M1's first audit. Every one passed a casual test run.

- **`assert detector(fixture, EXEMPT_PKG) == []` is a tautology.** The detector early-returns on its
  exempt package before opening the file, so it returns `[]` even for a path that does not exist.
  Five of them shipped. Exercise negative fixtures through a **non-exempt** package.
- **`if MODULE.exists():` around an assertion is a silent skip that survives a rename.** A genuinely
  leaking `hookd_command.py` failed correctly; renaming it to `hookd_cmd.py` turned the suite green.
- **A boundary rule keyed on one exact AST spelling passes on the idiomatic spelling of the same
  violation.** `fields["k"]` caught, `fields.get("k")` not. `x.attr == lit` caught,
  `y = x.attr; y == lit` not. `sys.platform` caught, `from sys import platform` not. Enumerate the
  idioms a builder would naturally reach for, then write the rule — never the one form the violation
  was first written in.
- **A negative fixture nobody asserts content on passes when emptied.** `fixture()` asserting mere
  existence is not a check.
- **`node.level == 0` in an AST import scan silently exempts every relative import.** `core/` importing
  `..store` (which owns `sqlite3`) passed every gate in the batch.
- **A non-recursive `glob("*.py")` where `rglob` was meant** — a subdirectory escapes analysis entirely.
- **`string_literals()` collecting `str` only makes every `bytes` literal invisible** to all literal
  rules. `b"-q0"`, `b"/proc/self/stat"` all clean. The transport layer is exactly where bytes appear.
- **An unasserted mutex.** Replacing `with _lock:` by `if True:` left the suite green while producing
  34 duplicate ULIDs in 160,000 — on the fleet's primary join key. Mutation-test the lock.
- **An injected clock that is silently ignored.** `new_ulid(now=...)` honoured the argument only if it
  exceeded the highest clock any previous caller saw, so determinism depended on process history.

**AST string-literal scans over `src/` must exempt docstrings and word-bound their tokens**, or every
rule over a common English word becomes a false positive: `Stop`, `Setup`, `Notification` are ordinary
prose in a fleet page, and `/proc` matches inside `/procedure`. **Tell:** if fixtures start using `#`
comments where a docstring belongs, a scan is already being worked around.

**A rule tested only against the form its author had in mind is untested against the form its
defeater will use.** Two rounds of planted violations failed 13 of 13 boundary tests and still missed
every evasion above, because the planted violations used each rule's own canonical form.


### The sharpest one: a test that supplies its own input shape (M1 final verification, 2026-09-17)

`signals/ordering.py` parsed `last_event_at` with `"%Y-%m-%dT%H:%M:%SZ"`. **No production writer emitted
that format** — the discovery lane wrote milliseconds, the hook lane microseconds with a UTC offset. The
parse raised, the `except` swallowed it, `is_live()` returned `False` for every row forever, and every
`running` session was silently demoted to `starting` at age 0 ms. §16's middle state value was
unreachable on the fleet page.

**444 tests were green**, because every fixture hand-wrote the one format the parser accepted. The tests
proved the parser agreed with the tests.

Two rules follow, and they generalise past this repo:

1. **A test whose input it writes itself proves only self-consistency.** Where a value crosses a seam,
   the test's input must come from the **real writer**. This project's first rule — *no data shape
   asserted without a real captured example* — applies to shapes we write ourselves, not just to a
   vendor's payloads.
2. **A swallowed `ValueError` that degrades to a quiet `False` is the failure mode principle 5 exists to
   prevent.** An unparseable stamp is an *unknown*, and an unknown is counted and displayed. Had it been,
   the anomaly counter would have read 100% on day one.

Corollary found in the same pass: `allow_reuse_address = False` on a server whose client holds a
permanent SSE connection makes same-port restart fail for the whole TIME_WAIT window — the normal path,
not a corner case. And a `python -m` entry point with no `if __name__ == "__main__"` guard prints
nothing and **exits 0**: a silent success, the same defect class as everything above.

### Mutation testing found what four green suites could not (M2 T12, 2026-09-17)

`shepherd replay` shipped with 72 green tests over its two modules. A reviewer mutated eight lines of
production code; **four mutations survived** (three control mutations were caught, so the harness was
real). A hunter reproduced seven defects with executable probes. The lesson is not "add more tests" —
it is that **a green suite is evidence about the tests, not about the code**, and mutation is the
cheapest way to tell the two apart. Every finding below is a shape, not an incident:

1. **A metric asserted only at its terminal value is untested.** All four assertions on the headline
   `unknown` rate expected exactly `0.0`; hardcoding the constant survived. Every rate needs one
   fixture at a **fractional** value, and the rendered string asserted too — `.1f` rounding is a
   second untested function hiding behind the first.
2. **Counters documented as separate need one fixture producing all of them at once.** `malformed` /
   `version` / `orphaned` were each tested in isolation, so folding two together survived. One
   assertion of `(1, 1, 1)` kills the whole mutation class.
3. **An idempotence assertion over two no-change runs compares the empty case.** The census loop never
   executed, so the "first-seen order → byte-identical" claim — which was *true* — was asserted by a
   comparison that could not observe it. Compare two **changing** runs.
4. **Write the safety artefact before the destruction, not after.** `--apply` wrote 412 verdicts, then
   the diff. The one order that makes the diff a safety property was unpinned by any test, and moving
   the write to the *safer* order also survived mutation.
5. **A filter argument compared as a raw string silently means "nothing".** `--since 30d` (the plan's
   own example) read zero records and exited **0**. Worse, the test asserted `read 0 records` — it had
   enshrined the bug as the specification. A passthrough test must assert a non-empty narrowing.
6. **A module-local "this error is not swallowed" contract is worth nothing without a test driving it
   through the outermost seam the user meets.** Three correct-looking layers composed into false
   remediation advice: `write_replay_diff` propagates (right), `registry.invoke()` converts every
   handler crash to one literal (`"request failed"`), and the CLI renders that as *"start the control
   daemon"* — told to a user whose database was just rewritten.
7. **A counter reading 0 because its path never ran.** A torn archive lost 44 of 50 records with
   `skipped_malformed == 0`, because the reader `return`ed from a generator and the abandoned lines
   never reached the counting layer. Byte-indistinguishable from a log that only held 6 records.
8. **An `except` tuple tested only against the damage form its author imagined.** Truncated gzip →
   `EOFError` (caught, and the test truncates). Corrupt gzip → `zlib.error`, which is not an
   `OSError` (uncaught).
9. **A cohort-narrowing `WHERE` clause silently relabels the rows it excludes as a different failure.**
   `WHERE stop_reason IS NOT NULL` sat two lines below `UNCLASSIFIED_SQL`'s `IS NULL`; the excluded
   cohort — the one the tool exists to fix — was reported as `orphaned`, i.e. "purged".
10. **A comment citing a boundary rule must name the test that enforces it.** Three docstrings cited
    P-M2-10 as law while `shepherd.logs` was absent from `FORBIDDEN_BELOW_L4`. The next builder reads
    the comment, believes the rule is mechanical, and it erodes silently.
11. **A guarantee can hold for a different reason than the code claims.** D25 held — no web route
    reaches `logs/` — but by the `API_ROUTES` whitelist, not by the `audiences={HUMAN}` set the
    docstring named, since the web layer supplies `Audience.HUMAN` itself. The invariant actually
    protecting the property was the unasserted one.
12. **An AST scan's forbidden-name set must match the node class those names appear as.** Four of six
    entries could never fire: they were matched against `ast.Call`/`ast.Name` while the real usage was
    an `ast.Attribute` or an annotation.

### A stale `.pyc` makes a mutation harness report phantom reds (M3 T3, 2026-09-17)

`EXPECTED_SCHEMA_VERSION = 2` → `= 3` is a **same-size write inside one mtime second**, which defeats
CPython's bytecode invalidation: the source on disk was correct and two tests failed anyway. Since
plant-and-revert mutation proof is now how this repo verifies that a check bites, this is not a
curiosity — a harness that does not clear `__pycache__` between runs can report a red that proves
nothing, or (worse, and in the same way) a **green** for a mutation that never actually loaded.
Clear `__pycache__` per mutation run.

### Two more vacuous-test shapes, both self-caught while being written (M3 T2/T3, 2026-09-17)

* **A test that hashes the same files the runner hashes.** `test_001_and_002_are_untouched` compared
  migration *versions*, which the runner derives from the same files the test built from — it agreed
  with itself and could not observe a forward-only violation. Rewritten to pin the recorded sha256.
* **A scan that lowercases one side of its comparison.** A banned-word check lowercased the literal
  but not the banned word, so `-L` was never matched at all; the fix then over-matched `-l` inside
  `"handle-less"`. Both directions now have self-checks. The rule: a scan needs a negative control
  proving it stays *quiet*, not only a positive one proving it fires.

### Pin a constant by parsing the document that states it (M3 T2, 2026-09-17)

Rather than retyping §11's caps and §8's timeout into a test, the test **parses them out of the spec
files**. A number typed in two places can agree with itself while both are wrong; a number read from
its source of truth cannot. Same instinct as deriving a totality expectation from
`itertools.product` over the real enums instead of writing `len(...) == 96`.

### An allowance by identity is not an exemption (M3 T2, 2026-09-17)

`core/` may not spell runner vocabulary, yet `AnomalyKind.TMUX_UNAVAILABLE`'s **value** must contain
`tmux` — it is the wire word a stored count is keyed by. Resolved without a rule-level carve-out:
the scan asserts **set equality against exactly one `(file, literal)` pair**, then asserts that
literal really is the enum member's value. A second leak still fires. A rule-level exemption would
have silenced it.

### A surviving mutation is either a test gap or a provably-dead check — distinguish them (M3 T17, 2026-09-17)

31 mutations of `web/ws.py`: 29 red, **2 survivors**. The two were short-header guards
(`len(buffer) < 4`, `len(buffer) < 10`) whose deletion left every test green. The builder did not
delete them and did not claim the coverage. It **proved** they were behaviour-neutral — a truncated
big-endian extended length can only shrink, so the caller's `offset + n + length` check answers "not
yet" either way — kept the guards, and wrote the argument, *including "the mutation run says so"*,
into the docstring. The same run found a **real** gap next door: the partial-frame test only cut a
7-bit-length frame, so a header truncated inside its own 16/64-bit length field was unexercised.
That one was closed.

The rule: never respond to a survivor by deleting the code it mutated (that silently narrows the
program) or by asserting the test suite is fine (that silently narrows the truth). Decide which it
is, in writing.

### Feed a spec's worked example to a parser that would reject it, without re-encoding (M3 T17)

RFC 6455 prints its fragmentation example **unmasked**; a server parser must *reject* unmasked
frames, so the example cannot be fed in directly — and re-encoding it through our own masker would
make the test prove only that our encoder and decoder agree. Resolution: set the mask bit with a
**zero mask key**. Masking is `payload[i] ^ key[i % 4]`, so a zero key is the identity: the RFC's
payload bytes remain verbatim in the hex and stay checkable by eye, while the frame is structurally
valid for a mask-requiring parser. The capture's real non-trivial key is what separately proves
masking is actually applied.

Generalises: when a fixture from an authority is in the wrong *frame* for the code under test,
look for a transform that is provably the identity on the part you care about — never a
re-encode through the thing being tested.

## Project SKILL_HINTS

None.


## Lessons from M4 and the QA pass (2026-09-21)

These cost real time and are recorded in `CLAUDE.md` and the ledgers. They are
here because this is the file a cc10x session loads first.

- **Clear `__pycache__` before every mutation run.** CPython decides a `.pyc`
  is fresh from (source mtime in whole seconds, source size). A mutation that
  preserves size and lands in the same second re-imports the *unmutated*
  bytecode and is recorded as a **false survivor** — a hole written down as a
  proof there isn't one.
- **A planted violation is an inert fixture that nothing imports.** A shadow
  tree isolates files, not signals, subprocesses or the host. See `CLAUDE.md`;
  the 2026-09-17 reboot is why.
- **`-L` on a tmux session is not enough.** A command run *inside* tmux inherits
  `$TMUX` and resolves to that socket, so pass `-L` on **every** invocation.
  `patterns.md` used to state this rule without that clause; the clause is the
  part that made it recur.
- **Per-task ledger files, not one shared ledger.** Four builders appending to
  one file lost two tasks' entries.
- **"Recorded" is not "applied".** A decision written into a ledger while the
  code still has the old behaviour happened twice in M4. Grep for the behaviour,
  not for the sentence.
- **Freeze a baseline on a quiet tree**, never while builders are writing.

### A control that exercises one gate certifies one gate (Phase 0, 2026-09-21)

Phase 0 built `tools/render_check.py` specifically so that later phases could not
claim verification they did not have — and shipped it with **two CRITICAL holes**,
both found by a review and a failure hunt run against the same diff.

The builder demonstrated a negative control: a page with a heading removed, which
failed correctly. That proved the **DOM assertion** bites. It was read — by the
builder and by me — as proving *the checker*. Four other gates in the same
function had never been driven at all.

1. **Drain the observation buffer after the observation, not before it.**
   `page.on("console", …)` registered at load and appended for the whole run, but
   the single read sat *above* the loop that opens the six pages. Every error the
   checker's own clicks provoked was collected and discarded at `page.close()`.
   The tool's stated contract — *"a console error is a failure"* — held for the
   first 700 ms, which is before it does any work. Registration is not
   observation: **grep for the read, not the subscribe.**
2. **Asserting presence is not asserting exclusivity.** The loop asserted the
   clicked page root was visible and never that the others were not. A page with
   no routing script at all scored `0 failures` and wrote twelve screenshots —
   *which is U18, the exact bug the tool was written for.* Verified against a
   faithful reproduction.
3. **The fix needs a fixture only the new branch can see.** Checking exclusivity
   at arrival alone made the reproduction fail while leaving the per-click branch
   dead code. The builder built a page that arrives clean and un-hides one root
   on every click, then deleted the branch in a scratch copy: mutant 0 failures
   exit 0, repo 10 failures exit 1.
4. **A missing locator must be reported, never clicked.** A missing
   `#drawer-open` raised a 30 s `TimeoutError`, losing every failure already
   collected *plus* the summary line — while a missing nav entry three lines
   above was handled correctly. The asymmetry was the tell.
5. **Report what was checked, not only what failed.** `0 failures` was
   byte-identical whether twelve assertions ran or none. This is the M2-T12
   *"counter reading 0 because its path never ran"* shape, one level up.
6. **A one-definition-site guard keyed on one spelling is defeated by the other
   quote style** — and single quotes were that module's own house style. Second
   recorded instance of this shape in this repo. Strip the definition lines and
   assert the token is *absent* from the remainder: quote-agnostic,
   order-agnostic, fails closed.
7. **`sys.modules` before `exec_module` has two halves.** Register before (or
   `dataclasses` cannot resolve annotations) *and* unregister on failure (or the
   next importer gets a half-initialised module).

**And a tool can silently constrain the product.** `esprima` 4.0.1 is an **ES2017**
parser — it rejects `?.`, `??`, class fields, `#private`, `||=`, optional catch
binding, `import.meta` and numeric separators — and it was a Required Check in six
later tasks that write three new modules. A gate that fails browser-correct code
either drags the code down to the parser's era or quietly stops being run. It now
parses in **chromium**, the engine the code actually runs in. Cost, recorded
rather than absorbed: no line number for a module compile error.

### Two agents on one branch share an INDEX, not just a tree (2026-09-22)

Commit `09d3d5d`'s message is entirely about retiring an assumption in a plan.
It also deletes `src/shepherd/signals/discovery.py` and its test — 125 lines —
and says nothing about it.

Nobody did anything unusual. A builder ran `git rm`, which **stages
immediately**. The router then ran `git add -A docs/plans .cc10x && git commit`,
and `git commit` commits **the whole index**, not the paths just added. So one
agent's staged deletion rode into another's documentation commit.

Nothing was lost and the tree is correct. What was lost is the *record*: a
reader looking for when discovery was deleted finds it under a message about
something else, and `git log -- <path>` points at the wrong intent.

**The rule: when more than one agent can write to a branch, commit by path, not
by index.**

```
git commit -m "…" -- docs/plans .cc10x      # only these paths, index ignored
```

not

```
git add -A docs/plans .cc10x && git commit  # everything staged, by anyone
```

The same session also saw `HEAD` move under a running builder twice, and a
second `pytest` running concurrently with a builder's own run. None of those
broke anything here, but they are the same family: **the branch is shared
mutable state, and only the working tree feels private.**

The cheaper structural answer is the one already in use for the UI phases —
give each parallel agent a worktree, which gives it its own index too — and to
keep in-place parallelism only for agents whose file sets are provably disjoint.

### A worktree is not cut from where you think, and presence alone cannot tell you (2026-09-22)

Every agent worktree this harness creates was cut from the **same old commit**,
25 behind the branch carrying the work it depended on. Phase 3's builder caught
it at pre-flight, before writing a line, because its brief carried a one-line
base check.

**The decisive signal was the symbol that was still there, not the one that was
missing.** The base lacked `create_project` — which on its own is equally
consistent with "stale base", "verb renamed", and "verb lives in another
module". What settled it was that `upsert_workspace` was **present**, and Phase 1
had deleted it.

So: **assert base validity with a presence check AND an absence check.**

```
git show HEAD:<file> | grep -c "def <new_symbol>"      # expect 1
git show HEAD:<file> | grep -c "def <retired_symbol>"  # expect 0
```

Presence alone cannot distinguish a stale base from a partial one.

Two more things worth keeping:

- **Check the base before the work, not after.** The cost here was one agent
  spin-up and no wasted code. The same gap discovered three tasks in would have
  produced work built against verbs that do not exist, and a RED that is a
  collection error rather than a behavioural failure — a **false RED**, which
  the contract rejects anyway.
- **Not every worktree is harmed by a stale base.** Two earlier ones were cut
  from the same commit and were fine, verified rather than assumed: their inputs
  (`core/stops.py`, `runner/pane.py`) were byte-identical across the gap. The
  question is never "is the base current" but "is the base current **for what
  this task reads**".

## Last Updated

2026-09-21.