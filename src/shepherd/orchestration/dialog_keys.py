"""T16's captured half: what the two dialogs look like, and which keys answer them.

**Pure.** Screen text in, a verdict out; a mapping out, never a keystroke. No
store, no runner, no clock, and nothing is sent from here — `dialogs.py` drives
the pane. The split is the one this repo has taken six times (`rows.py`,
`stops.py`, `signals/fields.py`, `reads.py`, `writes.py`, `trust.py`,
`admission.py`) rather than raise a size cap, and the halves are genuinely two
jobs: *what the captures say* versus *drive the pane*. Both halves assert their
own size so the split cannot hide growth.

**Only keys a capture shows cross this seam (K1).** P4's five rounds are the
whole permission vocabulary: `1` ran the tool, `2` ran it and widened the
allow-list, `3` did not run it, and the end-of-run listing is exactly those two
files. Enter selects whatever is highlighted, which at the un-amended dialog is
`1. Yes`.

**Both matchers are positional, because both screens are.** A digit selects the
option *at that position now*, and `Down` moves to the option *below*; neither
key carries its meaning with it. So the option set is matched in order, and a
screen that is not the captured one gets no key at all.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from shepherd.runner.pane import PERMISSION_MARKER, TRUST_MARKER

__all__ = [
    "ALLOW_OPTION_PREFIX",
    "DIALOG_EVIDENCE",
    "PERMISSION_KEYS",
    "TRUST_KEYS",
    "TRUST_OPTIONS",
    "PermissionChoice",
    "SidecarState",
    "is_the_captured_permission_dialog",
    "is_the_captured_trust_dialog",
]

PermissionChoice = Literal["approve", "approve_always", "deny"]

#: Option 2 is **directory-scoped** (`…access to <cwd> from this project`), so
#: only its stable head is matched: pinning the tail would refuse every dialog
#: raised anywhere but the probe's own throwaway directory.
ALLOW_OPTION_PREFIX = "Yes, and always allow access to "

#: The trust screen's two options, in the order every capture shows them.
TRUST_OPTIONS: tuple[str, ...] = ("No, exit", "Yes, I trust this folder")


class SidecarState(StrEnum):
    """What the engine's own live record says, as a value the gate is handed.

    Three members because `ABSENT` is a first-class answer, not a missing one:
    `None` would invite a caller to read "no file" as "nothing is waiting"
    (principle 5). The caller resolves the engine's own field names into one of
    these; none of them is spelled here.
    """

    WAITING = "waiting_on_a_dialog"
    NOT_WAITING = "not_waiting_on_a_dialog"
    ABSENT = "absent"


#: Enter selects the highlighted default `1. Yes`; `2` and `3` are P4's raw
#: bytes (`send-keys -H 32` / `-H 33`), which select an option and never land in
#: the input box.
PERMISSION_KEYS: Mapping[PermissionChoice, tuple[str, ...]] = {
    "approve": ("\r",),
    "approve_always": ("2",),
    "deny": ("3",),
}

#: Trusting is `Down` then `Enter`; a bare `Enter` is the refusal, and it leaves
#: the process dead with status 1. Two intents, two sequences, one map — and a
#: map that is not the one above, which is the whole point of two functions.
TRUST_KEYS: Mapping[bool, tuple[str, ...]] = {True: ("\x1b[B", "\r"), False: ("\r",)}

_HAZARDS = "tmux send-keys delivery hazards (programmatic write path)"
_TRUST = "Workspace-trust dialog (TUI, tmux capture-pane)"
_SIDECAR = "Session sidecar file ~/.claude/sessions/<pid>.json"

#: `<data-schemas.md section> · <what backs it>`, the shape `runner/pane.py` uses.
#: Captures are cited **by name** and resolved under `docs/probes/` by the
#: P-M3-16 test. The permission rows cite the write-path section rather than the
#: hook-payload one that carries the same screen: that heading names an engine
#: event, which `orchestration/` may not spell (the rule T13 tripped in draft).
DIALOG_EVIDENCE: Mapping[str, str] = {
    "approve": f"{_HAZARDS} · B-file-created.txt — Enter at the un-amended dialog ran the tool",
    "approve_always": f"{_HAZARDS} · 06a-2-dialog.txt, 99-cwd-listing.txt — 2 ran it and widened",
    "deny": f"{_HAZARDS} · 05a-3-dialog.txt, 99-cwd-listing.txt — 3 did not run the tool",
    "amended": f"{_HAZARDS} · 02a-tab-dialog.txt, 02b-tab-after.txt — Tab re-labels option 1",
    "sidecar": f"{_SIDECAR} · 06-sidecar-permission.json, 01-trust-dialog-sidecar.json — present"
    " while a permission dialog waits, absent by design during the trust dialog",
    "trust": f"{_TRUST} · 01c-trust-yes-selected.txt — Down then Enter selects the second option",
    "refuse_trust": f"{_TRUST} · 01b-list-sessions-after-refuse.txt — a bare Enter exits, status 1",
}

_OPTION = re.compile(r"^(\d+)\.\s+(.*?)\s*$")


def _unchevroned(line: str) -> str:
    """One screen line without its selection marker or its padding."""
    return line.lstrip().removeprefix("❯").strip()


def _numbered_options(text: str) -> tuple[tuple[int, str], ...]:
    """The run of numbered options that follows the question, in screen order.

    Read **after** the question line and stopped at the first line that is not
    an option, so a command body that happens to contain `1. ` cannot be mistaken
    for the option list it sits above.
    """
    found: list[tuple[int, str]] = []
    started = False
    for line in text.splitlines():
        if not started:
            started = PERMISSION_MARKER in line
            continue
        match = _OPTION.match(_unchevroned(line))
        if match is None:
            break
        found.append((int(match.group(1)), match.group(2)))
    return tuple(found)


def is_the_captured_permission_dialog(text: str | None) -> bool:
    """Exactly the three captured options, at exactly the captured positions."""
    if text is None:
        return False
    options = _numbered_options(text)
    return (
        len(options) == 3
        and options[0] == (1, "Yes")
        and options[1][0] == 2
        and options[1][1].startswith(ALLOW_OPTION_PREFIX)
        and options[2] == (3, "No")
    )


def is_the_captured_trust_dialog(text: str | None) -> bool:
    """The two captured options, in the captured order — `Down` is positional."""
    if text is None or TRUST_MARKER not in text:
        return False
    seen = tuple(o for line in text.splitlines() if (o := _unchevroned(line)) in TRUST_OPTIONS)
    return seen == TRUST_OPTIONS
