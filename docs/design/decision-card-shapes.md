# The decision card — the two dialog shapes, from captured evidence

**2026-09-21.** Reference for U17 (`docs/design/ui-decisions.md`). Every shape
below is copied from a real capture under
`docs/probes/2026-09-14-schemas/tmux-tui/`, which is frozen evidence. Nothing
here is reconstructed or tidied.

U11 says a `needs you` session shows **the engine's own prompt, numbered the way
the TUI numbers it**, and that Shepherd sends the keystroke. The parser that
does this has to survive two structurally different dialogs, and they differ in
exactly the way that is most dangerous to get wrong.

---

## Shape 1 — the permission dialog

`run-20260914T154946Z/06-permission-dialog.txt`, and identically in
`supp2-20260914T155625Z/B1-permission-dialog.txt`:

```
────────────────────────────────────────────────────────────────────────────────
 Bash command

   touch perm-probe.txt
   Create an empty file named perm-probe.txt

 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project
   3. No

 Esc to cancel · Tab to amend
```

- A full-width rule opens the box.
- A **title** line (`Bash command`).
- A body: the command, then its description.
- A **question** line ending in `?`.
- **Numbered** choices. The selected one carries `❯`; the others are indented.
- Footer: `Esc to cancel · Tab to amend`.

**Choice 2 is why U11 refuses to flatten this to approve/reject.** It carries
the scope — *always allow, for this path, from this project* — and it is usually
the one you actually want. Flattened, it is unreachable.

## Shape 2 — the trust dialog (C15)

`run-20260914T154946Z/01-trust-dialog.txt`, blank lines removed:

```
────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:
 /tmp/shp-tui-A-4tvrx00n
 Quick safety check: Is this a project you created or one you trust? …
 Claude Code'll be able to read, edit, and execute files here.
 Security guide
 ❯ No, exit
   Yes, I trust this folder
 Enter to confirm · Esc to cancel
```

**Three differences, and each one breaks a naive parser:**

1. **The choices are not numbered.** A parser keyed on `^\s*❯?\s*(\d+)\.` finds
   nothing here and, if it treats "no choices" as "not a dialog", reports the
   session as having no ask while it sits blocked forever.
2. **The default selection is the refusal.** `❯` is on `No, exit`. In the
   permission dialog `❯` is on `Yes`. So the position of the cursor carries
   opposite meaning in the two shapes, and **a blind Enter here exits the
   session** — which is C15, stated as a measurement rather than a worry.
3. **The footer differs** — `Enter to confirm · Esc to cancel` versus
   `Esc to cancel · Tab to amend`. It is the cheapest discriminator available
   and it is on screen in both.

## What this means for the parser

- **Parse the choice list positionally, not numerically.** A choice is a line in
  the block between the question and the footer; the number, when present, is a
  *label* to display and to send, not the thing that identifies the choice.
- **Never synthesise a default.** Report which line carries `❯` and let the page
  show it. Do not assume the first choice is the affirmative one — in shape 2 it
  is not.
- **Recognise the trust dialog explicitly** and refuse to auto-answer it. It is
  the one dialog where the safe-looking key is the destructive one.
- **Degrade, never guess** (U17). Anything that does not match a known shape
  renders as the ask plus approve/reject, and says that it could not read the
  choices. That is the same rule `unknown` follows everywhere else in this
  system.
- **Attached sessions render read-only.** We have no pty of theirs, so the card
  shows the ask and says it cannot answer — rather than three buttons that go
  nowhere.

## What this does not cover

Only two dialog shapes were captured, both on `claude` 2.1.270. The engine's
choices move with its version (U17 hazard 2), and there is no capture of: a
dialog with more than three choices, a dialog inside a subagent, or the
`Tab to amend` flow. The parser must therefore be written so an unknown shape is
a *degrade*, not an exception — and the probe corpus is the place to add the
next shape when one is seen.
