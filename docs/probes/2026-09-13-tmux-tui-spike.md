# Probe: tmux ↔ Claude Code TUI (spec §18, M3 precondition)

**Date:** 2026-09-13 · **claude:** 2.1.270 · **tmux socket:** `shepherd-spike` (throwaway, torn down by name)
**Verdict:** PASS — the M3 LocalRunner assumption (D14) holds, with three constraints the spec did not name.

The first attempt on 2026-09-12 opened with a bare `tmux kill-server` and killed the host session;
see spec §18 "Incident 2026-09-12" and `CLAUDE.md`. This run followed those rules.

## Results

| Check | Result | Evidence |
|---|---|---|
| TUI renders inside tmux | pass | banner, prompt box, status line captured |
| Alternate screen | pass | `#{alternate_on}` = 1 once the TUI is up (0 while the trust dialog shows) |
| Programmatic input | pass | `send-keys -l "<text>"` then `send-keys Enter` → model answered `PONG` |
| Live byte stream | pass | `pipe-pane -o "cat >> pty.log"` captured output as it arrived |
| Resize + reflow | pass | `resize-window -x 70 -y 30` → pane 70x30, widest captured line 70 cols |
| Late-attach resync | pass | `capture-pane -e -p -S -2000` → ANSI intact (57 escapes), contains prior output |
| Exit status | pass | with `remain-on-exit on`, `/exit` → `#{pane_dead}`=1, `#{pane_dead_status}`=0 |
| Session name with `:` | **fail** | `new-session -s shepherd:probe` silently became `shepherd_probe` |
| Title write-back (D29) | **pass** | `/rename <title>` typed into the pty → Claude Code itself appended `{"type":"custom-title","customTitle":...}` to its transcript |

## Constraints for the M3 plan

1. **Workspace trust dialog.** A fresh `claude` spawned into a directory it has never seen stops on
   "Quick safety check: Is this a project you created or one you trust?", with the default choice
   **"No, exit"**. It fires no hooks while waiting. A queue-worker worktree or any new cwd hits this.
   Spawn must handle it: detect the dialog in the pane and raise `needs_you`, or pre-trust the path.
   Never send a blind Enter — that picks "No, exit".
2. **Target syntax.** Use `=<name>:` for pane-scoped commands (`capture-pane`, `send-keys`,
   `set-option`, `list-panes`). `=<name>` alone resolves for session commands but fails for panes
   ("can't find pane" / "no such window").
3. **Socket collision on this host.** Spec §9 puts owned sessions on `tmux -L shepherd`, and the
   user's own live sessions already run on a socket named `shepherd` here. The socket name must be
   configuration; dev, test, and QA runs use a different name.

## D29 consequence

`can_set_title` can be `True` for **owned** sessions: the rename goes through the engine's own
`/rename` command over the pty, so we never write a file Claude Code owns (principle 4). It is a
programmatic write, so it follows the §9 write policy (immediate only when `stopped` or `needs_you`).
`title_synced_at` is set when the `custom-title` entry is read back from the transcript. **Attached**
sessions have no pty, so their renames stay `local only`.
