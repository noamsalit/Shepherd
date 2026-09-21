# Backlog: re-derive the pane rule table from macOS captures

**Written:** 2026-09-20, during the first macOS run of the tree.
**Status:** not actioned. Referenced from `src/shepherd/runner/pane.py::_is_live_screen`
and from the 2026-09-20 amendment to `docs/specs/orchestrator-platform.md` §LocalRunner.

## Why

`runner/pane.py`'s rule table was derived from **one host's** captures —
`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/`, taken on Linux
6.8 with tmux 3.4 and Claude Code 2.1.270. That is the right methodology (D41),
and it worked. What it cannot do is tell an essential property of the engine
from an incidental property of that host.

`alternate_on` was the one that came along for the ride. On Linux it is `1`
once the TUI is up, so it looked like a discriminator for "the engine is
drawing". On macOS 26.6 / tmux 3.6a a live, prompt-ready engine reports `0`
(`docs/probes/2026-09-20-macos-pane/`), and both engine 2.1.267 and 2.1.278 do,
so it is not version drift. Because `_is_prompt_ready` and `_is_busy` both built
on it, every healthy owned pane on a Mac classified `UNREADABLE` and was counted
as an anomaly — and `write_policy` maps `UNREADABLE` to `REFUSE_NO_PTY`, so
Shepherd could not send a keystroke to any owned session on macOS.

## What shipped instead, and what it leaves open

`_is_live_screen` now accepts `alternate_on or screen.has_input_line` — the
engine's own input frame, which `_read_screen` already finds portably, is the
direct evidence the bit was a proxy for. It is deliberately an `or` and not a
deletion: `docs/probes/2026-09-20-macos-pane/02-bare-shell.ansi` is the
checked-in negative that keeps a live non-engine pane reading `UNREADABLE`.

**The residual gap, stated so it is not rediscovered as a surprise:** on a host
where `alternate_on` is always `0`, an engine **mid-turn** — drawing, with no
input box on screen — still reads `UNREADABLE` rather than `BUSY`. It
under-reports a busy pane, and `write_policy` answers `REFUSE_NO_PTY` for it,
which refuses a write rather than mis-sending one. That is the safe direction,
and it is still wrong.

## The work

1. Run the `2026-09-14-schemas/tmux-tui` probe sequence on macOS: trust dialog,
   after-trust, after-stop, permission dialog, prompt-with-suggestion, resize,
   and a mid-turn capture — which the Linux run does **not** have, and which is
   exactly the row that would close the gap above.
2. Re-derive the `PANE_RULES` table from both corpora together, so every
   predicate is constrained by two hosts rather than one.
3. Keep `tests/runner/test_pane.py`'s discipline: captures read by path, never
   copied into fixtures; populations asserted against the directory listing, not
   hand-written lists.

## Size

A probe run and a table revision — an afternoon, not a week. The captures are
cheap; the judgement about which fields are essential is the work.

## Related

- `docs/probes/2026-09-20-macos-pane/SECTION.md` — the two captures and what was
  ruled out, with method.
- `docs/solutions/portability/linux-built-suite-on-macos.md` — the wider pattern
  this is an instance of: a rule derived on one host encoding that host's
  incidentals.
