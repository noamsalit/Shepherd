# M3 Task 1 probes P1-P4 — findings (2026-09-17)

Four `§Not verified` items M3's design depends on, closed before any code reads them. Written in
`docs/specs/data-schemas.md`'s entry shape. Every fenced example below is a byte substring of the
capture file named beside it — the fences were **injected from the files**, not typed from memory,
and `tests/test_m3_probes.py::test_findings_cite_real_capture_paths` checks every path here exists.

**Harness:** `docs/probes/2026-09-17-m3-tmux/probe_m3.py`, a copy of
`docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`'s harness with the plan's **two named
defects fixed in the copy** — the bare `tmux -V` is now the exact `VERSION_ARGV` form
`check_tmux_argv` allows, and the teardown socket is one of `shepherd-m3-probe` /
`shepherd-m3-outer` / `shepherd-m3-inner` instead of `shepherd-probe`. The original is frozen
evidence and was not edited. Beyond the two fixes, **every tmux argv this harness builds is run
through the product's own `check_tmux_argv` before execution**, twice — whole, and from the binary
onward so the `env -i` prefix cannot hide it (T8-2's `_tmux_tail` scan).

**Engine version — read this first.** The engine **self-updated from 2.1.273 to 2.1.274 during this
task**: the first P1 run and `drift_check.py` saw 2.1.273 at 11:03 UTC, P2 saw 2.1.274 at 11:04.
P1 was re-run so all four folders sit at one version. `drift_check.py` re-run at 2.1.274 reports no
drift on the checked surface (33 event names + 4 enums). Recorded as **BLOCKER-T1-1**.

**Not run, deliberately:** **P5** (`/rename` against a session live in another process) risks two
writers on one transcript; **P6** (xterm.js rendering) is not probeable on this host. Neither was
attempted and neither is reported here.

---

## P1 — Input-line editing keys in the Claude Code TUI (`C-a C-k`, `C-w`, and `C-u` on the post-`Esc` restored prompt)

- **Produced by:** claude 2.1.274 TUI (`claude-haiku-4-5`, real API) in tmux 3.4, socket `shepherd-m3-probe`
- **Consumed by:** DP10 / D45 (`WriteDecision.CLEAR_THEN_SEND` and its post-`C-u` pane re-read guard), T13's write policy, T14's `clear_input(handle)`
- **Probe:** `docs/probes/2026-09-17-m3-tmux/probe_m3.py`. Re-run: `PYTHONPATH=src .venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py --only p1`
- **Status:** verified live 2026-09-17

**Not re-probed:** plain `C-u` after a history recall. The repo already answers it —
`docs/probes/2026-09-14-schemas/gap-fill/keys-claude-20260914T180105Z/01b-after-ctrl-u.txt`.

**Real example** (full captures in `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/`).
`Esc` pressed while the turn was still in flight puts the submitted prompt back in the input box
(`04b-after-esc-restored.txt` line 43):

```text
❯ ESC-RESTORE-MARKER write a detailed 900-word essay on the history of terminal multiplexers, in full prose, no lists.
```

and `C-u` against **that restored prompt** clears it, leaving the same
`Ctrl+Y to paste deleted text` affordance the 2026-09-14 history-recall capture shows
(`04c-after-ctrl-u-on-restored.txt` lines 41-43):

```text
                                                                                                                                  Ctrl+Y to paste deleted text
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ 
```

| Key (`send-keys -t =<name>:`) | State it was sent in | Input box after | Evidence (under `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/`) |
|---|---|---|---|
| `C-a` then `C-k` | `ALPHA BRAVO CHARLIE` typed, not submitted | **empty** — the line is cleared | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/02a-before-ctrl-a-ctrl-k.txt` line 43 to `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/02c-after-ctrl-a-ctrl-k.txt` line 43 |
| `C-w` x1 | `WORDONE WORDTWO WORDTHREE` typed | `WORDONE WORDTWO` | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/03b-after-ctrl-w-x1.txt` line 43 |
| `C-w` x2 | same | `WORDONE` | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/03b-after-ctrl-w-x2.txt` line 43 |
| `C-w` x3 | same | **empty** | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/03b-after-ctrl-w-x3.txt` line 43 |
| `Escape` | turn **in flight** (`c_stop_before_esc: false`; the screen shows `esc to interrupt`) | the submitted prompt is **restored** into the box | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/04a-streaming-before-esc.txt`, `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/04b-after-esc-restored.txt` |
| `C-u` | the post-`Esc` **restored** prompt | **empty**, with `Ctrl+Y to paste deleted text` | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/04c-after-ctrl-u-on-restored.txt` |
| (re-read) | 1 s after the `C-u` | identical to the read before it (`c_reread_agrees: true`) | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/04d-reread-after-ctrl-u.txt` |

**Variants and edge cases:**
- `C-a C-k` is a two-key sequence and both keys are `send-keys` **key names**, not bytes — the same
  constraint T13-2 recorded for `C-u`. It is not expressible through `Runner.write(handle, bytes)`.
- The first run of this probe pressed `Escape` 4.5 s after `Enter` on a *short* turn; haiku had
  already finished and `Stop` had fired, so the `Esc` landed at an idle prompt and answered a
  question the repo already covers. The committed run reads back `c_esc_pressed_mid_flight: true`
  before it trusts the rest of step C. A run where that flag is false must be reported `unknown`.
- The trust dialog's default option is **`No, exit`**, not "yes". The harness now reads the
  selection back off the chevron line before pressing `Enter`; sending `Down`+`Enter` blind exited
  the pane (status 1) on the first attempt.

**Spec alignment:**
- **DP10 / D45 hold, and are now capture-backed for the case they were deferred on.** The post-`Esc`
  restored prompt is *not* a different widget: `C-u` clears it exactly as it clears a history
  recall. `WriteDecision.CLEAR_THEN_SEND` ships as designed.
- The post-`C-u` re-read guard agreed with the first read here. It is still the right guard — this
  is one observation, not a proof that it always agrees.
- `data-schemas.md` §Key semantics has no `C-a C-k`, `C-w` or `C-u` row. Three rows are owed there.

---

## P2 — `--resume <id> --fork-session` with `--session-id` and `--no-session-persistence`

- **Produced by:** claude 2.1.274, headless (`-p --output-format json`), throwaway `mktemp` cwd, explicit `--settings` per run
- **Consumed by:** §9 `ask()` (DP7 / DP2), `AnomalyKind.ASK_FORK_RESIDUE` (T2), T15, `data-schemas.md` §Fork
- **Probe:** `docs/probes/2026-09-17-m3-tmux/probe_m3.py`. Re-run: `PYTHONPATH=src .venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py --only p2`
- **Status:** verified live 2026-09-17

**Real example** (full captures in `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/`). The
`result` and `session_id` fields of the fork that was given an explicit `--session-id`
(`05-result-object-shape.json` lines 46-59, extracted from `02-fork-with-session-id.stdout.json`):

```json
 "result": {
  "type": "str",
  "example": "PINEAPPLE-M3"
 },
 "result_index": {
  "type": "int",
  "example": 0
 },
 "session_id": {
  "type": "str",
  "example": "356b6e66-635e-424c-80fd-fef653880906"
 },
```

| Question | Captured answer | Evidence (under `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/`) |
|---|---|---|
| Does `--resume <id> --fork-session` accept `--session-id <uuid>`? | **Yes.** `rc=0`, empty stderr, and the result object's `session_id` **is the uuid that was asked for** | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.argv.txt`, `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.stdout.json`, `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.stderr.txt` |
| Does that fork still answer from the target's context? | **Yes.** `result` = `PINEAPPLE-M3`, the codeword given only to the base session | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.stdout.json` |
| Does that fork leave a transcript? | **Yes** — `<newId>.jsonl` appears in the target's project dir | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-project-listing.txt` |
| Does `--no-session-persistence` apply with `-p` in that combination? | **Yes.** `rc=0`, the fork still answers `PINEAPPLE-M3`, and **no new file appears** | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/03-fork-nsp-with-session-id.stdout.json`, `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/03-project-listing.txt` |
| ...and without `--session-id` (control)? | Same: **no transcript left**; the engine generates the id and reports it in `session_id` | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/04-fork-nsp-no-session-id.stdout.json`, `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/04-project-listing.txt` |
| Does the result object still carry `session_id` at 2.1.274? | **Yes**, on all four runs | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/results.json`, `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/05-result-object-shape.json` |
| Are the four flags present at this version? | `--resume`, `--fork-session`, `--session-id`, `--no-session-persistence` all in `--help` | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/00-claude-help.txt` |

The result-JSON field table is appended to `docs/specs/data-schemas.md` §Fork, so K1 is satisfied in
the document and not only in a capture folder.

**Variants and edge cases:**
- The base session was created with `--session-id` too and its result `session_id` equalled the
  requested uuid, so `--session-id` is honoured at spawn *and* at fork.
- `--no-session-persistence` was checked by listing the project dir before, immediately after, and
  2 s later. A slower delete would have read as "left" on a tighter window; it did not here.
- Only the **fork's own** file was watched. The base transcript stayed in the listing throughout,
  but this probe did not hash it — "the target is untouched" remains the 2026-09-14 finding, not
  this one's.
- All four runs were `-p`. Forking a **live interactive** target while passing `--session-id` was
  not attempted; the 2026-09-14 live fork covers a live target *without* `--session-id`. The
  combination is **`unknown`**.

**Spec alignment:**
- **Contradiction.** `data-schemas.md` §Fork says *"A fork leaves a permanent transcript file in the
  target's project dir. `ask()` must delete it or filter it"*, and the M3 plan's T2 defines
  `AnomalyKind.ASK_FORK_RESIDUE` as *"P2 says a fork transcript is left; it is named, never
  deleted"*. **With `--no-session-persistence` no transcript is left at all** — `ask()` needs no
  delete step and `ASK_FORK_RESIDUE` fires only if the flag is dropped. Recorded as
  **BLOCKER-T1-2**; T2 and T15 both read this line.
- **Confirmation.** DP7's fallback rests on the result JSON, not on the sidecar, and the result JSON
  still carries `session_id` at 2.1.274.
- §18's fork risk is unchanged: the fork is a separate process with its own id.

---

## P3 — A browser-equivalent writer and a second attached tmux client typing at the same pane

- **Produced by:** claude 2.1.274 TUI in tmux 3.4. The inner socket `shepherd-m3-inner` holds the TUI; the second client is `env -u TMUX tmux -L shepherd-m3-inner attach` run from a pane on the **outer** socket `shepherd-m3-outer`, the shape the 2026-09-14 attach probe used
- **Consumed by:** DP9 / D40 (a human at `[tmux attach]` beside a live browser terminal), T14's delivery, `AnomalyKind.MAILBOX_INPUT_NOT_EMPTY`
- **Probe:** `docs/probes/2026-09-17-m3-tmux/probe_m3.py`. Re-run: `PYTHONPATH=src .venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py --only p3`
- **Status:** verified live 2026-09-17

**Real example** (full captures in `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/`).
Round 3 — the writer sent `Reply with only the word CONCURRENT` and pressed `Enter` while the
second client typed `Z`s (`results.json` lines 112-121):

```json
 "round3_submit_under_typing": {
  "user_prompt_submit_seen": true,
  "submitted_prompt": "Reply with only the word CONCURRENTZZZZZZZ",
  "client_noise_in_submitted_prompt": true,
  "input_box_after": [
   "\u276f Reply with only the word CONCURRENTZZZZZZZ",
   "\u276f\u00a0Z"
  ],
  "thread_errors": []
 },
```

| Round | What happened | Captured result | Evidence (under `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/`) |
|---|---|---|---|
| second client attaches | `env -u TMUX tmux -L shepherd-m3-inner attach -t =shepherd_p3:` from an outer pane | attaches; `list-clients` shows `attached,focused,UTF-8`; the client renders the TUI | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/02-attach-cmd.txt`, `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/04-inner-list-clients.txt`, `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/03-outer-client-view.txt` |
| 1 — sequential control | writer `send-keys -H` 20x`A`, then the client types 20x`B` | clean: `A`x20 then `B`x20, two runs, nothing lost | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/05-round1-sequential.txt` |
| 2 — concurrent | 10 writer bursts of `AAAA` and 10 client bursts of `BBBB`, released together by a barrier | **no bytes lost** (40 + 40) and **no burst torn** — but the two streams **interleave**: 19 runs, `AAAABBBBBBBBAAAABBBB...` | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/07-round2-concurrent.txt`, `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/results.json` |
| 3 — writer submits under typing | the writer writes a prompt and presses `Enter` while the client types `Z` | **the submitted prompt carries the human's keystrokes**: `UserPromptSubmit.prompt` = `Reply with only the word CONCURRENTZZZZZZZ`, and one `Z` is left behind in the box | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/results.json`, `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/09-round3-submitted.txt` |
| the client's view | after round 3 | tracks the inner pane; the title the engine set is visible in the client's status line | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/10-outer-client-view-final.txt` |

**Variants and edge cases:**
- The interleaving granularity is **one `send-keys` call**, not one byte: each 4-byte burst stayed
  contiguous. tmux serialises a single `send-keys`; it does not serialise a *sequence* of them
  against another client's typing.
- Round 2's one 8-long `B` run is two adjacent client bursts, not a torn write.
- `C-u` between rounds cleared the box both times, with the second client still attached.
- Only a **read-write** attach was probed. The 2026-09-14 probe covers `-f read-only`.
- Whether the same race can reach the *transcript* rather than the prompt was not measured.
  **`unknown`.**

**Spec alignment:**
- **Contradiction with the assumption behind DP9 / D40, and the sharpest one in this set.** "Do they
  interleave cleanly?" has a two-part answer: *no bytes are lost or torn*, **but the human's
  keystrokes end up inside the prompt Shepherd submits**. A pre-write check of the input line cannot
  close this — the human can type in the window between the check and the `Enter`. Recorded as
  **BLOCKER-T1-3**.
- `MAILBOX_INPUT_NOT_EMPTY` (T2 / T14) is the right counter for the case the check *does* catch, and
  this capture is why that deferral must exist. It is not a fix for the race.

---

## P4 — Permission-dialog key semantics: `1` / `2` / `3` / `Esc` / `Tab`

- **Produced by:** claude 2.1.274 TUI (`claude-haiku-4-5`, real API) in tmux 3.4, socket `shepherd-m3-probe`. The dialog is the **Bash-command** permission dialog, raised five times by `touch <file>`
- **Consumed by:** DP8 / D44 — `answer_permission`'s `approve` and **`deny`**, which had no captured mechanism; T13's `REFUSE_DIALOG`; T16
- **Probe:** `docs/probes/2026-09-17-m3-tmux/probe_m3.py`. Re-run: `PYTHONPATH=src .venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py --only p4`
- **Status:** verified live 2026-09-17

**Real example** (full captures in `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/`).
The dialog as it appears (`02a-tab-dialog.txt` lines 14-24):

```text
 Bash command

   touch perm-tab.txt
   Create an empty file named perm-tab.txt

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to /tmp/shp-m3-p4-vh9n71hn/work from this project
   3. No

 Esc to cancel · Tab to amend
```

After `Tab` the dialog is **still up** and **option 1 has changed meaning**
(`02b-tab-after.txt` lines 19-24):

```text
 Do you want to proceed?
 ❯ 1. Yes, and tell Claude what to do next
   2. Yes, and always allow access to /tmp/shp-m3-p4-vh9n71hn/work from this project
   3. No

 Esc to cancel
```

| Key sent | `send-keys` argv | Dialog after | Tool ran? | Hooks in that round | Evidence (under `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/`) |
|---|---|---|---|---|---|
| `Tab` | `send-keys -t =shepherd_p4: Tab` | **still up**; option 1 becomes `1. Yes, and tell Claude what to do next`; the footer drops `Tab to amend` | **no** | `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `Notification` | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/02a-tab-dialog.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/02b-tab-after.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/02d-tab-row.json` |
| `Esc` | `send-keys -t =shepherd_p4: Escape` | dismissed; the turn shows `Interrupted · What should Claude do instead?` | **no** | `UserPromptSubmit`, `PreToolUse`, `PermissionRequest` — **no `PermissionDenied`, no `Stop`** | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/03a-escape-dialog.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/03b-escape-after.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/03d-escape-row.json` |
| `1` | `send-keys -t =shepherd_p4: -H 31` | dismissed; the tool is approved | **yes** — `perm-1.txt` created | `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `Stop` | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/04a-1-dialog.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/04b-1-after.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/04d-1-row.json` |
| `3` | `send-keys -t =shepherd_p4: -H 33` | dismissed; `Interrupted · What should Claude do instead?` — **the same end state as `Esc`** | **no** | `UserPromptSubmit`, `PreToolUse`, `PermissionRequest` — **no `PermissionDenied`, no `Stop`** | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/05a-3-dialog.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/05b-3-after.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/05d-3-row.json` |
| `2` | `send-keys -t =shepherd_p4: -H 32` | dismissed; the tool is approved **and the directory is allow-listed for the project** | **yes** — `perm-2.txt` created | `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `Stop` | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/06a-2-dialog.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/06b-2-after.txt`, `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/06d-2-row.json` |

The cwd listing at the end is exactly `perm-1.txt`, `perm-2.txt`
(`docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/99-cwd-listing.txt`): the two
approving keys ran the tool, the three non-approving ones did not.

**Variants and edge cases:**
- **A digit is positional, and its meaning depends on dialog state.** After `Tab`, `1` means
  `Yes, and tell Claude what to do next`, not `Yes`. A `deny` implemented as "send `3`" is safe only
  against a dialog nobody has amended — and Shepherd cannot see an amendment it did not make.
  Recorded as **BLOCKER-T1-4**.
- Option 2's wording is **directory-scoped** here (`always allow access to <cwd> from this
  project`). Other tools raise other option sets; **only the Bash dialog was probed**, and the
  numbering is positional, so `2` is not a fixed meaning across dialogs.
- Neither refusal fired a `PermissionDenied` hook in the ~5 s window, and neither fired `Stop`. **A
  caller that waits on `PermissionDenied` to confirm its deny landed will wait forever.**
- The digits were sent as raw bytes (`-H 31` / `32` / `33`), never as `-l` text. They select the
  option; they do not land in the input box.
- Not probed, and therefore **`unknown`**: what a digit does at a permission dialog for a
  **non-Bash** tool; what `Enter` does after `Tab`; and whether a text reply follows `3` — the
  screen invites one (`What should Claude do instead?`) but this probe pressed `Escape` and moved on.

**Spec alignment:**
- **DP8 / D44's gap is closed for the Bash dialog.** `answer_permission(approve)` is `1`;
  `answer_permission(deny)` is **`3`**, and `Esc` reaches the same end state. Both were captured;
  neither was guessed.
- `data-schemas.md` §PermissionRequest and §Notification say nothing about key semantics. A row is
  owed in §Key semantics, with the positional caveat above.
- T13's `REFUSE_DIALOG` is confirmed as the right default: **`Tab` leaves a dialog up whose option 1
  now means something else**, which is exactly a state no programmatic writer should key into.

---

## Teardown

Every socket this task used, checked after the run that used it:

| Socket | `teardown.txt` | Line |
|---|---|---|
| `shepherd-m3-probe` | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/teardown.txt` | `no server running` |
| `shepherd-m3-probe` (witness; P2 starts no tmux server) | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/teardown.txt` | `no server running` |
| `shepherd-m3-outer` and `shepherd-m3-inner` | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/teardown.txt` | `no server running` (both) |
| `shepherd-m3-probe` | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/teardown.txt` | `no server running` |

`shepherd` — the user's socket — was read once, read-only, and never written to. `aivisor`, `main`
and `spike` were all still up afterwards.
