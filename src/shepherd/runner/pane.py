"""What is on the screen, as a pure function over real captures (T6).

**Pure.** Bytes and format fields in, one `PaneState` out — no I/O, no clock, no
process. The two calls that produce the bytes live in `runner/local.py` (T8), so
the write policy, the trust gate and the delivery trigger are all testable
against the checked-in probe captures with no live pane anywhere.

**Six rows, no seventh.** `PaneKind` is closed at six (`core/runner.py`) and the
write policy (T13) is total over 96 keys built from it. A screen that fits none
of the six is `UNREADABLE` **and counted**, never a quiet new member.

**`DEAD` and `BUSY` are decided on format fields and structure, not on text.**
`read_pane` consumes `capture-pane -e -p` bytes, and this repo's six such
captures include neither a running pane nor a dead one — both exist only as plain
`-p` `.txt`. A text rule for either would assert a byte shape production never
produces, and would collide with this module's own negative: plain bytes cannot
separate ghost text from a draft. So `DEAD` is `pane_dead == 1` alone, and `BUSY`
is the **residual** — a live alternate screen with no dialog and no input line.
`DEAD_MARKER` is vocabulary, deliberately not a detector;
`test_dead_is_decided_by_pane_dead_alone` fails if it becomes one again.

**Ghost text is never input.** The TUI draws its prompt suggestion in the input
box in SGR 2 (dim), and plain `-p` output cannot tell it from something the user
typed — the trap `data-schemas.md` names outright. `input_text` is the non-dim
run, `ghost_text` the dim one.

**A dead pane is not an anomaly.** It carries a real exit status, so counting it
would be principle 5 upside down. Only `UNREADABLE` counts, with a detail string
naming **which** absence was seen.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.runner import PaneFields, PaneKind, PaneState

#: The per-pane fields the listing prints, one pane per line. Seven fields,
#: joined by the character the listing already uses
#: (`14-list-sessions-after-sigterm.txt`).
PANE_FORMAT = (
    "#{alternate_on}|#{pane_dead}|#{pane_dead_status}|"
    "#{pane_title}|#{pane_width}|#{pane_height}|#{pane_pid}"
)

FIELD_SEPARATOR = "|"

#: The stable sentence on the workspace-trust screen (`01-trust-dialog.ansi`).
TRUST_MARKER = "Quick safety check: Is this a project you created or one you trust?"

#: The permission dialog's question (`06-permission-dialog.ansi`). On its own it
#: is only half the detector — the numbered option line is the other half.
PERMISSION_MARKER = "Do you want to proceed?"

#: What tmux itself draws over a dead pane (`13-dead-pane.txt`). **Vocabulary,
#: not a detector**: there is no `-e` capture of a dead pane in this repo, and
#: `pane_dead` answers the question without one.
DEAD_MARKER = "Pane is dead (status "

#: The input box: `❯` then a non-breaking space, between two `────` rules.
INPUT_PREFIX = "❯ "

_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_OSC8 = re.compile(r"\x1b\]8;[^\x07\x1b]*(?:\x07|\x1b\\)")
_RULE = re.compile("─{4,}")
_PERMISSION_OPTION = re.compile(r"^\s*(?:❯\s*)?1\.\s*Yes", re.MULTILINE)

_DIM_ON = "2"
_DIM_OFF = frozenset({"", "0", "22"})


@dataclass(frozen=True)
class Screen:
    """The decoded capture: its text, and the input box if it has one."""

    text: str
    input_text: str | None
    ghost_text: str | None

    @property
    def has_input_line(self) -> bool:
        return self.input_text is not None


@dataclass(frozen=True)
class PaneRule:
    """One row: `evidence` is `<data-schemas.md section> · <what backs it>`, and
    `test_every_pane_rule_cites_an_existing_section` asserts the section exists and
    that every capture path right of the separator is on disk."""

    kind: PaneKind
    detect: Callable[[PaneFields, Screen | None], bool]
    evidence: str


# ----- the format line --------------------------------------------------------


def parse_pane_fields(line: str) -> PaneFields:
    """One line of `PANE_FORMAT` output. Raises `ValueError` on anything else.

    A half-read listing is refused rather than defaulted — a pane reported alive
    because a field was missing is the guess principle 5 forbids — and the title,
    the one free-text field, is carved out from both ends so that a separator
    inside it cannot shift `pane_pid` by one.
    """
    head = line.split(FIELD_SEPARATOR, 3)
    if len(head) != 4:
        raise ValueError(f"a pane format line has 7 fields: {line!r}")
    tail = head[3].rsplit(FIELD_SEPARATOR, 3)
    if len(tail) != 4:
        raise ValueError(f"a pane format line has 7 fields: {line!r}")
    alternate, dead, status = head[0], head[1], head[2]
    title, width, height, pid = tail

    return PaneFields(
        alternate_on=_flag(alternate, "alternate_on"),
        pane_dead=_flag(dead, "pane_dead"),
        pane_dead_status=_optional_int(status, "pane_dead_status"),
        pane_title=title or None,
        width=_required_int(width, "pane_width"),
        height=_required_int(height, "pane_height"),
        pane_pid=_optional_int(pid, "pane_pid"),
    )


def _flag(value: str, field: str) -> bool:
    if value not in {"0", "1"}:
        raise ValueError(f"{field} is 0 or 1, not {value!r}")
    return value == "1"


def _optional_int(value: str, field: str) -> int | None:
    """Empty is a real observation: no exit status while the pane is alive."""
    if value == "":
        return None
    return _required_int(value, field)


def _required_int(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{field} is not a number: {value!r}") from error


# ----- the screen -------------------------------------------------------------


def _plain(text: str) -> str:
    """The text a reader sees: SGR runs and OSC 8 hyperlinks removed."""
    return _SGR.sub("", _OSC8.sub("", text))


def _dim_flags(line: str) -> list[tuple[str, bool]]:
    """Every character of `line` paired with whether SGR 2 was active for it."""
    found: list[tuple[str, bool]] = []
    dim = False
    position = 0
    for match in _SGR.finditer(line):
        found += [(character, dim) for character in line[position : match.start()]]
        for code in match.group(1).split(";"):
            if code == _DIM_ON:
                dim = True
            elif code in _DIM_OFF:
                dim = False
        position = match.end()
    found += [(character, dim) for character in line[position:]]
    return found


def _read_input_box(line: str) -> tuple[str, str | None]:
    """`(input_text, ghost_text)` for one input line: the dim run is never input."""
    characters = _dim_flags(_OSC8.sub("", line))
    visible = "".join(character for character, _ in characters)
    start = visible.index(INPUT_PREFIX) + len(INPUT_PREFIX)
    body = characters[start:]
    typed = "".join(character for character, dim in body if not dim).strip()
    ghost = "".join(character for character, dim in body if dim).strip()
    return typed, ghost or None


def _read_screen(capture: bytes) -> Screen | None:
    """`None` when the bytes are not a screen at all: empty, or not UTF-8."""
    if capture == b"":
        return None
    try:
        text = capture.decode("utf-8")
    except UnicodeDecodeError:
        return None

    lines = text.split("\n")
    plain = [_plain(line) for line in lines]
    for index, rendered in enumerate(plain):
        if not rendered.startswith(INPUT_PREFIX):
            continue
        if index == 0 or index + 1 >= len(plain):
            continue
        if _RULE.search(plain[index - 1]) and _RULE.search(plain[index + 1]):
            typed, ghost = _read_input_box(lines[index])
            return Screen(text="\n".join(plain), input_text=typed, ghost_text=ghost)
    return Screen(text="\n".join(plain), input_text=None, ghost_text=None)


# ----- the table --------------------------------------------------------------


def _is_trust_dialog(fields: PaneFields, screen: Screen | None) -> bool:
    return screen is not None and not fields.alternate_on and TRUST_MARKER in screen.text


def _is_permission_dialog(fields: PaneFields, screen: Screen | None) -> bool:
    return (
        screen is not None
        and PERMISSION_MARKER in screen.text
        and _PERMISSION_OPTION.search(screen.text) is not None
    )


def _is_live_screen(fields: PaneFields, screen: Screen | None) -> bool:
    """A live engine screen: the alternate screen, **or** the engine's own frame.

    `alternate_on` alone was the rule until 2026-09-20, and it is not portable.
    It was never evidence about the engine — it is a terminal *mode*, and it was
    standing in for "the TUI is drawing". On Linux 6.8 / tmux 3.4 / Claude Code
    2.1.270 the two coincided (`run-20260914T154946Z/02-after-trust-fmt.txt`
    records `alternate_on=1` once the TUI is up). On macOS 26.6 / tmux 3.6a they
    do not: a live, prompt-ready engine reports `alternate_on=0`
    (`docs/probes/2026-09-20-macos-pane/`), and since `_is_busy` and
    `_is_prompt_ready` both build on this predicate, **every** healthy owned pane
    on this platform fell through the table to `UNREADABLE` — and was counted as
    an anomaly. `write_policy` maps `UNREADABLE` to `REFUSE_NO_PTY`, so Shepherd
    could not send a keystroke to any owned session on a Mac.

    Not the engine version (2.1.267 and 2.1.278 both report `0` here) and not a
    tmux fault (a synthetic `\\033[?1049h` pane on the same socket reports `1`):
    the engine simply does not take the alternate screen on this host.

    `screen.has_input_line` is the **direct** evidence the bit was a proxy for —
    the engine's own input box, a `─{4,}` rule above and below a line starting
    `❯ `, which `_read_screen` already finds portably.

    **The narrowing is deliberate and the residual gap is recorded, not an
    oversight.** This is `or`, not "drop `alternate_on`". Dropping it would make
    `_is_busy` the residual for any readable non-dialog pane, so a bare shell
    would read `BUSY` instead of `UNREADABLE` and `_is_trust_dialog`'s
    `not alternate_on` clause would stop discriminating anything
    (`02-bare-shell.ansi` is the checked-in negative). What this `or` does not
    recover is the other half: on a host where `alternate_on` is always `0`, an
    engine **mid-turn** — drawing, with no input box — still reads `UNREADABLE`
    rather than `BUSY`. That is a real limitation of this predicate and the
    honest smaller one: it under-reports a busy pane, and `write_policy` answers
    `REFUSE_NO_PTY` for it, which refuses a write rather than mis-sending one.

    The proper fix is a macOS capture run and a table re-derived from it, the way
    the Linux rows were (`docs/backlog/2026-09-20-pane-table-macos.md`).
    """
    return (
        screen is not None
        and not fields.pane_dead
        and (fields.alternate_on or screen.has_input_line)
    )


def _is_prompt_ready(fields: PaneFields, screen: Screen | None) -> bool:
    return _is_live_screen(fields, screen) and screen is not None and screen.has_input_line


def _is_busy(fields: PaneFields, screen: Screen | None) -> bool:
    return _is_live_screen(fields, screen) and screen is not None and not screen.has_input_line


_TRUST_SECTION = "Workspace-trust dialog (TUI, tmux capture-pane)"
#: Cited to the **write-path** section, not the hook-payload one: it carries the
#: same screen and its heading names no engine hook event, which `runner/` may not
#: spell (`tests/boundaries/test_engine_vocabulary.py`).
_PERMISSION_SECTION = "tmux send-keys delivery hazards (programmatic write path)"
_LISTING_SECTION = "tmux list-sessions -F pane state (remain-on-exit on)"
_CAPTURE_SECTION = "tmux capture-pane output (-p, -e, -S -2000) for the Claude Code TUI"
_RUN = "run-20260914T154946Z"

#: Ordered, and the order is part of the rule: a dead pane is dead whatever the
#: bytes say, a dialog outranks the screen behind it, `BUSY` is what is left, and
#: `UNREADABLE` is the total row, so the table cannot fall through.
PANE_RULES: tuple[PaneRule, ...] = (
    PaneRule(
        kind=PaneKind.DEAD,
        detect=lambda fields, screen: fields.pane_dead,
        evidence=(
            f"{_LISTING_SECTION} · format field: pane_dead == 1, printed for every pane "
            f"({_RUN}/14-list-sessions-after-sigterm.txt). No capture is consulted"
        ),
    ),
    PaneRule(
        kind=PaneKind.TRUST_DIALOG,
        detect=_is_trust_dialog,
        evidence=f"{_TRUST_SECTION} · -e capture: {_RUN}/01-trust-dialog.ansi",
    ),
    PaneRule(
        kind=PaneKind.PERMISSION_DIALOG,
        detect=_is_permission_dialog,
        evidence=f"{_PERMISSION_SECTION} · -e capture: {_RUN}/06-permission-dialog.ansi",
    ),
    PaneRule(
        kind=PaneKind.PROMPT_READY,
        detect=_is_prompt_ready,
        evidence=(
            f"{_CAPTURE_SECTION} · -e captures: {_RUN}/03-after-stop.ansi, "
            f"{_RUN}/09-resize-after-70x30.ansi"
        ),
    ),
    PaneRule(
        kind=PaneKind.BUSY,
        detect=_is_busy,
        evidence=(
            f"{_CAPTURE_SECTION} · derived: the residual once the four positive kinds are "
            "excluded. No capture is cited because this kind asserts no byte shape; its "
            "evidence is the -e captures that define what it is not"
        ),
    ),
    PaneRule(
        kind=PaneKind.UNREADABLE,
        detect=lambda fields, screen: True,
        evidence=(
            f"{_CAPTURE_SECTION} · derived: principle 5 — bytes that are not a screen we can "
            "classify are a counted unknown, never a guessed kind"
        ),
    ),
)


# ----- the function -----------------------------------------------------------


def read_pane(
    capture: bytes, fields: PaneFields, anomalies: list[Anomaly] | None = None
) -> PaneState:
    """Classify one pane. Never raises, for any bytes.

    `anomalies` is the caller's sink, the shape the transcript reader already uses:
    `UNREADABLE` appends one `AnomalyKind.PANE_UNREADABLE` naming which absence was
    seen; every other kind appends nothing — a dead pane least of all.
    """
    screen = _read_screen(capture)
    for rule in PANE_RULES:
        if not rule.detect(fields, screen):
            continue
        if rule.kind is PaneKind.UNREADABLE and anomalies is not None:
            anomalies.append(
                Anomaly(
                    kind=AnomalyKind.PANE_UNREADABLE,
                    detail=_unreadable_detail(capture, screen),
                    engine_session_id=None,
                )
            )
        return _state(rule.kind, fields, screen)
    raise AssertionError("PANE_RULES ends in a total row")  # pragma: no cover


def _unreadable_detail(capture: bytes, screen: Screen | None) -> str:
    """Three absences, one member — the shape `TRANSCRIPT_TAIL_ABSENT` uses."""
    if capture == b"":
        return "empty capture"
    if screen is None:
        return f"capture is not UTF-8 ({len(capture)} bytes)"
    return f"no recognisable screen structure ({len(capture)} bytes)"


def _state(kind: PaneKind, fields: PaneFields, screen: Screen | None) -> PaneState:
    dialogs = (PaneKind.TRUST_DIALOG, PaneKind.PERMISSION_DIALOG)
    readable = screen if kind is not PaneKind.DEAD else None
    return PaneState(
        kind=kind,
        fields=fields,
        input_text=(readable.input_text or "") if readable is not None else "",
        ghost_text=readable.ghost_text if readable is not None else None,
        dialog_text=(screen.text if screen is not None and kind in dialogs else None),
    )


# ----- the decision -----------------------------------------------------------


@dataclass(frozen=True)
class Choice:
    """One option the engine is offering, read positionally."""

    number: int | None
    label: str
    selected: bool


@dataclass(frozen=True)
class DecisionPrompt:
    """What the screen is asking, and the options it offers, verbatim."""

    kind: PaneKind
    text: str
    choices: tuple[Choice, ...]

    @property
    def selected(self) -> Choice | None:
        for choice in self.choices:
            if choice.selected:
                return choice
        return None


#: The footer both captured shapes draw, and the cheapest discriminator on
#: screen: `Esc to cancel · Tab to amend` (permission) and
#: `Enter to confirm · Esc to cancel` (trust) share exactly this much.
DIALOG_FOOTER = "Esc to cancel"

#: The cursor. It marks *which* line is selected and nothing more: in the
#: permission dialog it sits on `Yes`, in the trust dialog on `No, exit`, so
#: reading it as "the affirmative" answers C15 by exiting the session.
CURSOR = "\u276f"

_CURSOR_LINE = re.compile(r"^(\s*)\u276f(\s*)")
_NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")
_LEADING = re.compile(r"^\s*")

#: The two kinds whose `dialog_text` is populated (`_state`). Every other kind —
#: a prompt-ready pane included, and its screen carries `\u276f` lines too — is
#: asking nothing, and asking it for a decision is how an idle session grows a
#: card it should not have (U11/E20).
_DECIDABLE = (PaneKind.TRUST_DIALOG, PaneKind.PERMISSION_DIALOG)

#: A block of one is not evidence of a choice list. Both captured shapes offer
#: two or more, so a single aligned line above the footer degrades rather than
#: becoming a one-option decision nobody has ever seen the engine draw.
_MINIMUM_CHOICES = 2


def read_decision(state: PaneState) -> DecisionPrompt | None:
    """What the pane is asking, or `None` — never a guess (U17, E16).

    **Pure.** A `PaneState` in, a `DecisionPrompt` or `None` out: no I/O, no
    clock, no process, and nothing that could answer the dialog it just read. The
    module that reads the trust screen must not be able to press Enter on it,
    because on that screen Enter answers *"No, exit"* (C15, E17).

    **Positional, never numeric.** The permission dialog numbers its options and
    the trust dialog does not (`docs/design/decision-card-shapes.md`). A parser
    keyed on the numbered form finds nothing in the trust screen, and if "no
    choices" is read as "not a dialog" a blocked session reports no ask while it
    sits there forever. So a choice is **a line in the block between the box and
    the footer**, and the number, when present, is a label to display and to
    send — not the thing that identifies the choice.

    **The structure it requires, and the four ways it degrades.** The footer
    line; a cursor line above it; every line from the cursor to the footer
    starting at the cursor's own label column, with no second cursor among them;
    and a rule line above, opening the box whose body is the ask. Any of the four
    absent and the answer is `None` — which T8.2 renders as the ask plus
    approve/reject, saying it could not read the choices. Only two shapes were
    ever captured, both on `claude` 2.1.270, so an unrecognised screen has to be
    a degradation and not an exception.
    """
    if state.kind not in _DECIDABLE or not state.dialog_text:
        return None

    lines = [line.rstrip() for line in state.dialog_text.split("\n") if line.strip()]

    footer = _last(lines, lambda line: DIALOG_FOOTER in line)
    if footer is None:
        return None

    cursor = _last(lines[:footer], lambda line: _CURSOR_LINE.match(line) is not None)
    if cursor is None:
        return None

    choices = _read_choices(lines[cursor:footer])
    if choices is None:
        return None

    rule = _last(lines[:cursor], lambda line: _RULE.search(line) is not None)
    if rule is None:
        return None
    text = _dedent(lines[rule + 1 : cursor])
    if not text:
        return None

    return DecisionPrompt(kind=state.kind, text=text, choices=choices)


def _last(lines: list[str], matches: Callable[[str], bool]) -> int | None:
    """The **last** match, not the first: the permission capture's scrollback
    holds the operator's own cursor-prefixed prompt lines well above the box."""
    for index in reversed(range(len(lines))):
        if matches(lines[index]):
            return index
    return None


def _indent(line: str) -> int:
    match = _LEADING.match(line)
    return len(match.group(0)) if match is not None else 0


def _read_choices(block: list[str]) -> tuple[Choice, ...] | None:
    """`block[0]` carries the cursor; the rest must align under its label."""
    head = _CURSOR_LINE.match(block[0])
    if head is None:  # pragma: no cover - _last already matched this line
        return None
    column = len(head.group(0))

    read = [_choice(block[0][column:], selected=True)]
    for line in block[1:]:
        if CURSOR in line or _indent(line) != column:
            return None
        read.append(_choice(line[column:], selected=False))

    if len(read) < _MINIMUM_CHOICES:
        return None
    return tuple(read)


def _choice(body: str, *, selected: bool) -> Choice:
    """The number is a label, and it is optional: the trust dialog has none."""
    numbered = _NUMBERED.match(body)
    if numbered is None:
        return Choice(number=None, label=body.strip(), selected=selected)
    return Choice(number=int(numbered.group(1)), label=numbered.group(2).strip(), selected=selected)


def _dedent(body: list[str]) -> str:
    """The ask as the engine drew it, shifted left but never reflowed."""
    if not body:
        return ""
    common = min(_indent(line) for line in body)
    return "\n".join(line[common:] for line in body).strip()
