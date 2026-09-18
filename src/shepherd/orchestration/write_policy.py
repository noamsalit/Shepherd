"""The write policy — one pure, total decision over a 96-key space (T13, §9).

**The key is a 4-tuple** — `(SessionState, PaneKind, Ownership, input_empty)`,
4 x 6 x 2 x 2 = **96** (ADR-M3-5, C-M3-3). `input_empty` is a *pane* fact and a
**key field**, not a fifth state: it is what makes `CLEAR_THEN_SEND` a row of its
own, and `REFUSE_INPUT_NOT_EMPTY` — the outcome of the caller's re-read — is
reachable only through it. Collapse it and the space is 48, the clearing rows
vanish, and a message is concatenated onto somebody's half-written prompt.

**Totality is asserted as a set equality against `itertools.product`, never as a
length** (`test_the_key_set_equals_the_product`). `len(WRITE_RULES) == 96` is
forbidden: a dropped `input_empty=False` row with a duplicate elsewhere passes it
while bytes go into a pane this table meant to refuse.

**Pure.** No clock, no store, no runner, and — the point — **no sending**. This
module decides; T14 and T18 act.

**D44 is built in rather than bolted on.** §9's "`needs_you` -> write
immediately" row is right for a question in the transcript and wrong for an open
permission dialog: the dialog *discards* the text and the `Enter` that follows
selects the default `1. Yes`, approving a tool the human never saw. So the
dialog is a pane kind, not a session state, and every state refuses it.

**The pane half of C-M3-4 only.** DP8 option (d) wants the sidecar *and* the pane
text clear before a write, and an absent sidecar counted rather than read as
clear. This module takes values, not sources, and its published signature carries
no sidecar field, so it closes the pane half: every `PERMISSION_DIALOG` key
refuses and `UNREADABLE` never sends. The sidecar half is T16's dialog gate
(`AnomalyKind.SIDECAR_ABSENT`). Recorded as T13-1.

**Every `ATTACHED` key is `REFUSE_NO_PTY`** — 48 of the 96. An attached session
runs on the user's own socket (K6): Shepherd has no pane there it may drive, and
§9 renders the read-only banner instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from shepherd.core.runner import PaneKind, PaneState, WriteDecision
from shepherd.core.states import Ownership, SessionState

#: `(state, pane kind, ownership, input_empty)`. One rule per tuple, no more.
WriteKey = tuple[SessionState, PaneKind, Ownership, bool]


@dataclass(frozen=True)
class WriteRule:
    """One key, one decision, and the capture that backs it.

    `evidence` is `<data-schemas.md section> · <what backs it>`, the shape
    `runner/pane.py` already uses, and
    `test_every_write_rule_cites_an_existing_section` (P-M3-16) asserts both
    halves: the section is in the document and every capture path is on disk.
    """

    state: SessionState
    pane: PaneKind
    ownership: Ownership
    input_empty: bool
    decision: WriteDecision
    evidence: str


_CAPTURES = "tmux capture-pane output (-p, -e, -S -2000) for the Claude Code TUI"
_LISTING = "tmux list-sessions -F pane state (remain-on-exit on)"
_HAZARDS = "tmux send-keys delivery hazards (programmatic write path)"
_KEYS = "Key semantics in the Claude Code TUI (history, bracketed paste, Ctrl-C, Esc)"

#: Captures are cited **by name** and resolved against `docs/probes/` by the
#: P-M3-16 test: the directory holding the `C-u` capture is `keys-claude-<date>`,
#: which `tests/signals/test_verdict.py`'s model-id rule reads as a model id (T13-3).
_E_PERMISSION = (
    f"{_CAPTURES} · 06-permission-dialog.ansi — text sent here is discarded and the Enter"
    " that follows selects the default `1. Yes` (D44)"
)
_E_TRUST = (
    f"{_CAPTURES} · 01-trust-dialog.ansi — a bare Enter at the trust screen selects"
    " `No, exit` (C15, A11)"
)
_E_READY = (
    f"{_KEYS} · 03-after-stop.ansi and A1-suggestion.ansi are empty boxes (ghost text excluded,"
    " E-M3-5); A2-typed-over-suggestion.ansi is a draft, and 01b-after-ctrl-u.txt is what C-u"
    " leaves behind — so the caller clears, re-reads, and only then writes (D45, DP10)"
)
_E_BUSY = (
    f"{_HAZARDS} · a turn is running, so the write is queued and delivered at the next turn"
    " boundary or prompt-ready pane (D12, D45); BUSY is runner/pane.py's residual classification"
)
_E_NO_PANE = (
    f"{_LISTING} · 14-list-sessions-after-sigterm.txt — a dead pane"
    " carries an exit status and no input line; an unreadable one is not clear either (principle 5)"
)
_E_ATTACHED = (
    f"{_LISTING} · an attached session lives on the user's own socket (K6), so Shepherd has no"
    " pane it may drive; §9 renders the read-only banner instead"
)

_SEND = WriteDecision.SEND_NOW
_CLEAR = WriteDecision.CLEAR_THEN_SEND
_QUEUE = WriteDecision.QUEUE
_DIALOG = WriteDecision.REFUSE_DIALOG
_NO_PTY = WriteDecision.REFUSE_NO_PTY

#: The owned half, written out: `(state, pane) -> (empty box, drafted box, evidence)`.
#: Twenty-four literal cells, never a comprehension over the product — a table
#: generated from `itertools.product` grows with its enums and could not fail
#: `test_the_key_set_equals_the_product` in the direction that matters.
_CELLS: Mapping[tuple[SessionState, PaneKind], tuple[WriteDecision, WriteDecision, str]] = {
    (SessionState.STOPPED, PaneKind.PERMISSION_DIALOG): (_DIALOG, _DIALOG, _E_PERMISSION),
    (SessionState.STOPPED, PaneKind.TRUST_DIALOG): (_DIALOG, _DIALOG, _E_TRUST),
    (SessionState.STOPPED, PaneKind.PROMPT_READY): (_SEND, _CLEAR, _E_READY),
    (SessionState.STOPPED, PaneKind.BUSY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.STOPPED, PaneKind.DEAD): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.STOPPED, PaneKind.UNREADABLE): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    # D44: a dialog is a different kind of `needs_you` than a question.
    (SessionState.NEEDS_YOU, PaneKind.PERMISSION_DIALOG): (_DIALOG, _DIALOG, _E_PERMISSION),
    (SessionState.NEEDS_YOU, PaneKind.TRUST_DIALOG): (_DIALOG, _DIALOG, _E_TRUST),
    (SessionState.NEEDS_YOU, PaneKind.PROMPT_READY): (_SEND, _CLEAR, _E_READY),
    (SessionState.NEEDS_YOU, PaneKind.BUSY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.NEEDS_YOU, PaneKind.DEAD): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.NEEDS_YOU, PaneKind.UNREADABLE): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.RUNNING, PaneKind.PERMISSION_DIALOG): (_DIALOG, _DIALOG, _E_PERMISSION),
    (SessionState.RUNNING, PaneKind.TRUST_DIALOG): (_DIALOG, _DIALOG, _E_TRUST),
    (SessionState.RUNNING, PaneKind.PROMPT_READY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.RUNNING, PaneKind.BUSY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.RUNNING, PaneKind.DEAD): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.RUNNING, PaneKind.UNREADABLE): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.STARTING, PaneKind.PERMISSION_DIALOG): (_DIALOG, _DIALOG, _E_PERMISSION),
    (SessionState.STARTING, PaneKind.TRUST_DIALOG): (_DIALOG, _DIALOG, _E_TRUST),
    (SessionState.STARTING, PaneKind.PROMPT_READY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.STARTING, PaneKind.BUSY): (_QUEUE, _QUEUE, _E_BUSY),
    (SessionState.STARTING, PaneKind.DEAD): (_NO_PTY, _NO_PTY, _E_NO_PANE),
    (SessionState.STARTING, PaneKind.UNREADABLE): (_NO_PTY, _NO_PTY, _E_NO_PANE),
}


def _expand() -> tuple[WriteRule, ...]:
    """Each cell becomes four rows: both `input_empty` values, both ownerships."""
    rules: list[WriteRule] = []
    for (state, pane), (empty, drafted, evidence) in _CELLS.items():
        for input_empty, decision in ((True, empty), (False, drafted)):
            rules.append(WriteRule(state, pane, Ownership.OWNED, input_empty, decision, evidence))
            rules.append(
                WriteRule(state, pane, Ownership.ATTACHED, input_empty, _NO_PTY, _E_ATTACHED)
            )
    return tuple(rules)


#: One rule per key. The **key set** is 96; the length is only ever checked
#: against the size of that set.
WRITE_RULES: tuple[WriteRule, ...] = _expand()

_BY_KEY: Mapping[WriteKey, WriteDecision] = {
    (rule.state, rule.pane, rule.ownership, rule.input_empty): rule.decision
    for rule in WRITE_RULES
}

#: What the UI renders. A refusal is a **state**, never a failure: nothing broke,
#: and §12's fleet page has no word for "failed" that would be true here.
_TEXT: Mapping[WriteDecision, str] = {
    WriteDecision.SEND_NOW: "ready — the input line is empty and the pane is waiting",
    WriteDecision.CLEAR_THEN_SEND: (
        "clearing the input line, then re-reading the pane before anything is sent"
    ),
    WriteDecision.QUEUE: "queued — this session is mid-turn; it is delivered at the next prompt",
    WriteDecision.REFUSE_DIALOG: (
        "waiting on you — a dialog is open in this pane, and only an explicit approve or deny"
        " answers it"
    ),
    WriteDecision.REFUSE_NO_PTY: (
        "read-only — there is no live terminal here for Shepherd to write to. If this session"
        " wasn't started here, open it in the platform to get one."
    ),
    WriteDecision.REFUSE_INPUT_NOT_EMPTY: (
        "deferred — there is unsent text on the input line; the message is kept and retried"
    ),
}


def decide_write(state: SessionState, pane: PaneState, ownership: Ownership) -> WriteDecision:
    """The one lookup. Total, pure, and it never raises.

    `pane` is projected onto the key's fourth field — `input_text` is draft text
    only, ghost text having been separated by `read_pane` (E-M3-5), so a
    placeholder can never be mistaken for something a human typed.

    A key that is not in the table — a state, kind or ownership from outside its
    enum — degrades to `REFUSE_NO_PTY`, the same answer an unreadable pane gets:
    a key we cannot place is a pane we cannot write to. It is never converted
    into a send.
    """
    key = (state, pane.kind, ownership, pane.input_text == "")
    return _BY_KEY.get(key, _NO_PTY)


def refusal_text(decision: WriteDecision) -> str:
    """What a human reads. Total over `WriteDecision`, so it cannot fall off the end."""
    return _TEXT.get(decision, _TEXT[_NO_PTY])
