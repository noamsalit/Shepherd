# T8.1 remediation — the choice list was anchored on the cursor, and the floor was doing its job alone

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: code-reviewer)
- Base: `44c26cc` on `integration`
- Files touched: `src/shepherd/runner/pane.py`,
  `tests/runner/test_pane_decision.py` — and this file. Nothing else.
- Python: `/root/Shepherd/.venv/bin/python`
- `tests/runner` was **82 green** before a line of this was written. Nothing here
  was red; what is fixed is unearned green.

## The shape of the whole thing, once

`read_decision` took `lines[cursor:footer]` as the choice list. The cursor is not
the top of the list — it is **wherever the person or the engine last left it** —
so the parser's answer changed with a keystroke that changes nothing about what
is being asked. The counter-example was already in the corpus and had never been
read: `01c-trust-yes-selected.txt`, the trust dialog with `❯` on the second of
its two options. **A capture that proves a variable is variable is worth as much
as the one showing its default**, and this one sat unused for a week while the
parser truncated.

Measured against `44c26cc`, permission dialog, cursor walked down its own three
options (nothing else changed):

| cursor on | `choices` | tail of `text` |
|---|---|---|
| option 1 | `[1, 2, 3]` | `…Do you want to proceed?` |
| option 2 | **`[2, 3]`** | `…Do you want to proceed?\n  1. Yes` |
| option 3 | **`None`** | — |
| `01c` (trust, option 2 of 2) | **`None`** | — |

Row 2 is the wrong parse the review named: option 1 leaves the list and reappears
as the last line of the engine's question, and U11's reason for existing — choice
2 carries the scope and must stay reachable — is destroyed by the same arithmetic
one position over. Rows 3 and 4 are the same bug at the last-option boundary,
where `_MINIMUM_CHOICES` caught the one-line block and turned a wrong answer into
a degradation. **That is the floor doing a second job it was never designed for,
and it is why C1 is fixed before C2.**

## What is wrong, and what it is now

| # | Defect | Fix |
|---|---|---|
| **C1** | the block started *at* the cursor (`:509`), so every option above the cursor was swept into the ask by `_dedent(lines[rule + 1 : cursor])` | the block is found **structurally**: the contiguous run of lines at one *label column* between the box rule and the footer, of which exactly one carries the cursor. `_label_column` counts `❯` as part of the gutter — the TUI draws it *in place of* the two-space indent — so a selected line and an unselected one begin at the same column and the run is the same run whichever member is marked. The cursor's only remaining job is to say which `Choice.selected` is `True` |
| **C2** | `_MINIMUM_CHOICES = 1` left **all 17 tests green**, and rendered the workspace-trust dialog as a one-choice card whose only choice is *"Yes, I trust this folder"* — C15 through the front door | `test_a_single_aligned_line_is_not_a_choice_list`, keyed on `01c` minus its `No, exit` line, plus `assert pane_module._MINIMUM_CHOICES == 2` because the mutilation row only bites at `1` and a floor of `3` would be invisible to it. Shown red at 1, green at 2 (below) |
| **H3** | four degradation rows drove **three** branches, and `if cursor is None: return None` was executed by no test in the suite: deleting ` ❯ 1. Yes` left `_last` matching the *operator's own* scrollback line (capture line 21, well above the box), so the row tripped alignment instead. `:485` and `:518` were uncovered too | the cursor is now searched **inside the box only** (`cursor <= rule` degrades), which is what makes the cursor-absent row reachable at all; each `return None` carries a `# degrade: <tag>` comment; `test_each_degradation_row_drives_its_own_branch` traces `read_decision` with `sys.settrace` and asserts the row returned through the branch it names; `test_every_degradation_branch_is_driven_by_a_row` fails if the source grows a branch no row reaches. **Eight branches, eight rows, no branch shared** |
| **H4** | the "no answering verb" guard was `re.search(r"answer\|send\|press\|key\|enter\|confirm", name)` over `dir(pane)` — and the verb that sends keystrokes in this repo is `LocalRunner.write` (`local.py:385`, `send-keys -H`), with `clear_input` and `interrupt` beside it. None matches, and the assertion had no control proving it could ever be non-empty | the property asserted is the **import surface**: `pane.py` imports nothing outside `__future__`, `re`, `collections.abc`, `dataclasses`, `shepherd.core.anomalies`, `shepherd.core.runner`. A `write`, `respond`, `submit`, `choose` or `deliver` needs a handle, a transport or a process whatever it is called. **The control is `local.py`**, which fails the same predicate and names `subprocess` |
| **M5** | two copies of "which kinds are dialogs": `dialogs` at `:373` gated `dialog_text`, `_DECIDABLE` at `:430` gated `read_decision`. Drift there is a populated `dialog_text` that `read_decision` answers `None` for — a session with a visible ask reporting no ask | one exported `DIALOG_KINDS`, referenced twice, with `test_the_kinds_that_carry_a_dialog_are_the_kinds_that_can_be_asked` walking **all six** `PaneKind` members over the same `dialog_text` |
| **M6** | every mutilation row operated on the permission capture, and `break_alignment` was keyed on the literal `"   3. No"`, which exists only there: one shape of two certified | the rows are a `Shape` × `Row` table over **three** captures — permission, trust with `❯` on the first option, trust with `❯` on the last. 20 mutilation cases where there were 4 |
| **L7** | `isinstance(result, DecisionPrompt)` is guaranteed by the return type and `seen == len(lines) + 1` counts a variable incremented once per iteration: two assertions that read as population guards without being any | dropped. The test's real content — no prefix of a capture raises — is kept, and now runs over all three shapes |

## The traced branch table (the H3 evidence)

`.venv/bin/python -m pytest tests/runner -q` → **128 passed**. Traced live, one
row per line, control column is the unmutilated capture:

```
row                                    shape                    branch taken
the footer is gone                     all three                no footer
the box rule is gone                   all three                no rule
the cursor line is gone                all three                no cursor in the box
a choice is dedented out of the block  permission, trust        the block does not reach the footer
a second line carries the cursor       all three                a second cursor
only the selected choice is left       all three                below the two-choice floor
the ask above the block is gone        all three                no ask above the block
an idle prompt-ready pane              03-after-stop.ansi       not a dialog
```

Every control traced to `None` (i.e. parsed). The dedent row is absent for `01c`
and says so in the table rather than being faked: that shape's cursor is on the
**last** option, so it has no line below the cursor to dedent — and dedenting the
line *above* it would land on the floor branch, which is a different row's job.

## Mutation proofs

Run with `__pycache__` cleared before **and** after each mutation (CLAUDE.md §4 —
`= 2` → `= 1` preserves file size, which is exactly the shape that re-imports
stale bytecode and records a false survivor).

| mutant | result |
|---|---|
| `_MINIMUM_CHOICES = 1` | **7 red**, including `test_a_single_aligned_line_is_not_a_choice_list` and the `only the selected choice is left` row on all three shapes. Restored to `2` → 128 green |
| `if cursor is None or cursor <= rule:` → `if cursor is None:` (the box bound dropped — H3's original defect, reconstructed) | **1 red**: `the cursor line is gone · permission`, `- no cursor in the box / + the block does not reach the footer`. Only the permission shape shows it, because only that capture has the operator's `❯` scrollback line above the rule |
| a second `# degrade:` tag duplicated | red at the `two branches tagged` assertion in `degrade_branches` |

## What this does **not** prove

- **More than three choices has never been captured.** Every shape here has two
  or three. A four-option dialog, or one that wraps a long label onto a second
  line, is unproven — and a wrapped label is the shape most likely to break the
  "one label column" rule, since a continuation line would sit at the same column
  and be read as a choice.
- **No subagent dialog exists in the corpus**, and no Tab-to-amend flow: the
  permission footer says `Tab to amend` and nothing in this repo has ever seen
  what the screen after that Tab looks like.
- **The block's upper bound is the box rule, not a blank line.** In
  `06-permission-dialog.ansi` the command lines (`   touch perm-probe.txt`) sit at
  **column 3 — the choice column** — and are kept out of the block only by the
  indent-1 ` Do you want to proceed?` line between them. An engine that drew its
  question at column 3 would have it read as a choice. That is a real residual
  and the reason the degrade rule stays structural: this parser answers `None`
  for anything it does not recognise, and T8.2 renders the ask with
  approve/reject when it does.
- **Two shapes, one engine build.** Everything here is `claude` 2.1.270 on Linux,
  from `run-20260914T154946Z`. The parser is not evidence about any other build.
