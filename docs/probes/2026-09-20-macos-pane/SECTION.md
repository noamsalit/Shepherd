# Capture — a live Claude Code pane on macOS does not take the alternate screen (2026-09-20)

**Host.** macOS 26.6.2 (Darwin 25.6.0, arm64), **tmux 3.6a**, Claude Code **2.1.278**.
The Linux corpus these sit beside — `2026-09-14-schemas/tmux-tui/run-20260914T154946Z/` — was
captured on Linux 6.8 with **tmux 3.4** and Claude Code **2.1.270**.

**Why it exists.** `src/shepherd/runner/pane.py`'s `_is_live_screen` required `alternate_on`, on
the strength of the Linux run (`02-after-trust-fmt.txt` records `alternate_on=1` once the TUI is
up) and of two rows in `docs/specs/orchestrator-platform.md` §LocalRunner that state outright that
"Claude Code's TUI runs on the alternate screen". On this host it does not, and because both
`_is_prompt_ready` and `_is_busy` were built on that predicate, **every healthy owned pane
classified as `UNREADABLE`** and was counted as an anomaly. `write_policy` maps `UNREADABLE` to
`REFUSE_NO_PTY`, so Shepherd could not send a keystroke to any owned session on a Mac.

## The two captures

Both are `tmux capture-pane -e -p`, taken on throwaway socket `shepherd-m3-probe` (`-L` on every
invocation, per `CLAUDE.md` rule 1; the server was killed on the same socket afterwards).

| file | what it is | `alternate_on` | bytes | classifies as |
|---|---|---|---|---|
| `01-prompt-ready-normal-screen.ansi` | Claude Code 2.1.278, trusted workdir, sitting at its prompt | **0** | 2211 | `PROMPT_READY` |
| `02-bare-shell.ansi` | `sh -c 'sleep 90'` — a live pane that is **not** the engine | **0** | 45 | `UNREADABLE` |

The `-fmt.txt` files carry the seven fields of `PANE_FORMAT`, in that order, separated by `|`:
`#{alternate_on}|#{pane_dead}|#{pane_dead_status}|#{pane_title}|#{pane_width}|#{pane_height}|#{pane_pid}`.
**Four redactions in `01-prompt-ready-normal-screen.ansi`, and what they cost.** This repo is
public, and the pane was captured on a real workstation, so four spans were replaced in place
before it was committed: the operator's absolute settings path and the permission warning quoting
it (two wrapped lines), one startup-hook error from an unrelated third-party tool that names that
tool's own login commands, and the random per-run segment of the scratch path. Each is replaced by
a `<redacted: …>` marker of visible text, so the screen's line structure, the ANSI runs around it
and the byte offsets of everything below are undisturbed — the capture went 2211 → 1994 bytes and
still classifies `PROMPT_READY`.

None of the four is load-bearing. Every redaction sits **above** the input frame, and the frame —
a `─{4,}` rule, a line beginning `❯ `, another rule — is the entire basis on which
`_is_live_screen` and `_is_prompt_ready` decide. `alternate_on=0`, the property this capture
exists to record, is in the `-fmt.txt` file and was never touched. Stated plainly because this is
edited evidence in a corpus whose whole discipline is that captures are read by path and never
copied: **the bytes are real and the redacted spans are not**, and anything asserting on the text
above the frame would be asserting on a marker rather than on a capture.

`pane_title` is redacted to `<redacted: host name>` — it is a host identifier, not session content,
and no assertion reads it (`data-schemas.md` redacts the Linux one the same way).

**The second capture is the load-bearing one.** It is what makes the fix a narrowing rather than a
deletion: a pane that is live and readable but is *not* the engine must keep classifying
`UNREADABLE`, or `_is_trust_dialog`'s `not alternate_on` clause stops discriminating anything and a
bare shell starts reading `BUSY`.

## What was ruled out, and how

* **Not a broken capture.** 2211 bytes, valid UTF-8, unchanged across 180 s of polling. The input
  box is plainly in it: a `─{4,}` rule, a line beginning `❯ `, another rule.
* **Not the engine exiting.** `pane_dead=0` throughout; `pane_current_command` stayed `2.1.278`.
* **Not engine drift (G12).** `2.1.267` and `2.1.278` were each started in a pane on this host, in
  an already-trusted directory: **both** report `alternate_on=0`, both readable, both with the
  caret present. If this were version drift the older engine would have differed.
* **Not tmux misreporting the field.** A synthetic pane running
  `sh -c 'printf "\033[?1049h"; sleep 20'` on the same socket reports `alternate_on=1`.

What is *not* settled is whether the cause is macOS or tmux 3.6a — separating them needs tmux 3.4
on a Mac or 3.6a on Linux, neither of which this host has. It does not change what Shepherd must
do: `alternate_on` is not a portable signal for "the engine's TUI is drawing", and the engine's own
frame is.

## Reproduce

```sh
S=shepherd-m3-probe
FMT='#{alternate_on}|#{pane_dead}|#{pane_dead_status}|#{pane_title}|#{pane_width}|#{pane_height}|#{pane_pid}'
tmux -L $S new-session -d -s eng -x 160 -y 45 -c <a trusted dir> 'claude --model claude-haiku-4-5'
sleep 28
tmux -L $S capture-pane -e -p -t eng   # the screen
tmux -L $S list-panes   -t eng -F "$FMT"
tmux -L $S kill-server                 # -L, always
```

## Status

These bytes are the regression test: `tests/runner/test_pane.py` classifies them by path, with no
live pane anywhere, which is this repo's idiom for pane rules and the reason the rule cannot
silently regress. The **proper** fix is a full macOS capture run with the table re-derived from it
rather than one predicate widened — recorded at
`docs/backlog/2026-09-20-pane-table-macos.md`.
