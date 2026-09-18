# M3 milestone verification

You are verifying that **M3 (owned sessions) is done**, against its own acceptance criteria. You are
not reviewing code quality and you are not fixing anything. You decide, clause by clause, **PASS /
FAIL / UNVERIFIED**, and the only currency you accept is a command you ran and its output.

## The criteria

`docs/plans/2026-09-17-m3-owned-sessions-plan.md`, section **"## Milestone acceptance — M3 is done
when"**. **There are SEVENTEEN clauses.** Read the whole section — do not read it through a `sed`
window. M2's verifier was briefed on 13 of its 16 clauses because a window cut three, and two of the
three FAILs it did find were in the part it had seen. Count them yourself and say the number you
counted before you score anything.

Score **every** clause. A clause you cannot check is **UNVERIFIED with the reason**, never a silent
PASS and never a PASS "by inspection".

## Five wording items already known — read these before scoring, they are not yours to discover

These are recorded in `docs/plans/2026-09-17-m3-BLOCKERS.md`. They are places where the **acceptance
text itself** is wrong or over-claims, and a verifier who scores them literally will either
over-credit or under-credit the tree. Judge each one and say whether you agree with the disposition:

1. **T-ACC-14** — clause 14 says "25 boundary test **modules**". The tree has **12 modules / 51
   rules**. "23 shipped" was M2's count of *rules*. The clause is comparing a rule count to a module
   count.
2. **T13-1** — clause 4's "both the sidecar and the pane text must be clear" does **not** close in
   T13. It closes at **T16**. Scoring clause 4 against T13 alone over-credits it.
3. **T12-3** — clause 7's "`crashed` is now reachable" names the *ingredient* (the exit code G-M2-2
   said was missing), not the literal: **no M3 path spells `StopReason.CRASHED`**.
4. **Task 18's exit criterion** ("M1's route tests pass unchanged") contradicts its own `Produces`,
   which adds two routes to a set those tests assert is closed. One of the two is wrong.
5. **Clause 14** also says `core/anomalies.py` grew by **seven** members. It is now **ten**
   (`MAILBOX_CLIENT_ATTACHED` from P3, `DIALOG_TEXT_UNRECOGNISED` from P4, and a corrected
   `ASK_FORK_RESIDUE` docstring). The property the clause protects — **appended at the end, none
   reordered** — still holds, and that is the thing to check, not the number.

## How to verify, in this repo

**The dominant defect class here is "checks that report success without checking."** A green test is
not evidence that a property holds; it is evidence that a test passed. For each clause, the question
is *what mutation would this check survive*.

- Where a clause rests on a check, **plant the violation and confirm the check goes red.** Plant only
  in **`scratchpad/m3-verify/shadow/`** — `cp -a src tests pyproject.toml docs` into it, strip
  `__pycache__`, run pytest with `cwd=` the shadow. Shadow **both** `src/` and `tests/`: boundary
  rules resolve the repo root from the test file. **Never plant in the real tree**, and never in a
  path whose default target is a real user file (a planted round-trip write in `trust_state` once
  hit the user's real `~/.claude.json`).
- A check with no mutation proof and no obvious bite is **UNVERIFIED**, not PASS.
- Two known precedents worth applying: T18 planted `decode(errors="replace").encode()` and it
  **survived** a byte-identity test over a clean UTF-8 capture; and a cross-origin mutation went red
  at the route level while the unit-level handshake test stayed green. Layered checks can each cover
  a different half; say which half you proved.

## Rules

- **Read-only on the product.** You may write only your report and your own shadow tree.
- **Never run `tmux kill-server` without `-L`.** The user's live sessions are on socket `shepherd`
  — never name it. Throwaways are `^shepherd-m3-`. **Do not hard-code the session names**: they
  change whenever the user opens a terminal (they were `aivisor`/`main`/`spike` before the
  2026-09-17 reboot). Read the list at the start of your run and again at the end, and assert it is
  unchanged *across your run*.
- **Never write under `~/.claude/`**; `~/.claude/settings.json` must stay at sha256
  `375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac`. Check it before and after.
- The default run excludes the `live` marker deliberately. If a clause needs the live lane, run
  `.venv/bin/pytest tests/e2e -m live` **only** after checking every tmux argv it will issue.
- Do not `git commit`. `docs/probes/` is read-only frozen evidence.

## Report

A table of all 17 clauses with PASS / FAIL / UNVERIFIED and, per clause, the command you ran and the
output that decided it. Then: the mutations you planted and their verdicts; every clause whose
**wording** you judge wrong (with the correction); and the final numbers — suite, mypy, boundary
rules, `~/.claude/settings.json` hash, `tmux -L shepherd ls`.

M2's verification returned FAIL on 2 of 16, and both were the plan claiming proof it did not have.
**That is the expected yield of a good verification, not a sign something went wrong.**

## Four more items found after this brief was first written — read these too

6. **DP2 option 2 reverses a finding M2's live lane still asserts** (BLOCKER-T24-2). M3 decided that
   a hooked `claude -p` run is marked `ephemeral` on the next sweep and therefore **hidden from the
   fleet page** — `Store.fleet()` is `WHERE s.ephemeral = 0`. M2's live clause *"the fleet page's
   tree carries the row's bucket"* is now **false by design**, not broken, and BLOCKER-T19-1 recorded
   the opposite behaviour before the decision existed. T24 re-pointed the two affected checks to
   assert the new truth **positively** (`row.ephemeral is True` **and** `tree_row() is None`), so the
   hiding is a claim the lane makes rather than an absence it tolerates. **Scoring any fleet-page
   clause without knowing this will produce a wrong verdict in one direction or the other.** Say
   which document you think should carry the reconciliation.

7. **14 of `test_ws.py`'s 25 tests exercise a parser `src/` never calls.** `ws.parse_frame`,
   `ws.WebSocketClosed`, `ws.Frame` and `ws.close_code` have no call site anywhere in `src/`;
   `web/server.py` never reads the upgraded socket (T19-c). Two of those tests assert a "read more
   and ask again" contract with **no implementer**. A fix was dispatched to record the vacuity with a
   boundary rule rather than to delete the parser or wire a read loop. **When you score acceptance
   clause 10, count only the tests whose subject the product actually runs**, and say how many of the
   clause's evidence you found to be of this kind.

8. **There is no browser→pane keystroke path in this tree** (BLOCKER-T19-c) — `POST_ROUTES` has no
   `terminal_write` and the upgraded socket is never read. `send-keys -H` byte-exactness is proved at
   the `Runner` seam, the contract and the write path, and **not** on the browser path. Any clause
   that reads as if the browser can type is over-claiming.

9. **A check exists that no plan task asked for:** `tests/e2e/test_live_lane_typechecks.py`, a mypy
   gate that runs in the **default** lane over the files only the live lane executes. It exists
   because T8-3's required new argument sat broken in two `live`-marked call sites for hours — the
   default run never executes them and `mypy --strict` covers `src` only. A deselected test is green,
   so nobody looks. Judge whether it does what it claims; its own mutation proof is that, with the
   arity break planted back, it names both sites.
