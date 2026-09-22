"""T8.1: the decision the screen is asking for, read off a `PaneState`.

**Read by path out of `docs/probes/`, never from a fixture copy.** Three captures
carry a dialog, and they disagree about the one thing that matters — where the
cursor is. In `06-permission-dialog.ansi` `❯` sits on *Yes*; in
`01-trust-dialog.ansi` it sits on *No, exit*; and in `01c-trust-yes-selected.txt`
it sits on the **second and last** option of the same trust screen. A parser that
reads the cursor as "the safe default" answers C15's trust dialog by exiting the
session, and a parser that anchors the *list* on the cursor loses every option
above it.

**`01c` is why the shapes are read structurally.** It is frozen evidence that the
cursor is a variable, not a constant of the shape, and it sat in the corpus
unused while the parser truncated. **The capture that proves a variable is
variable matters as much as the one showing its default.**

**Every degradation has a negative control, and each row names — and now
*proves* — the single branch it drives.** Phase 0 shipped a checker whose one
control certified one of five gates. The first version of this file repeated the
shape it warned about: four mutilation rows trod three branches, and the one
they all shared was not the one two of them named. So each `return None` in
`read_decision` is tagged `# degrade: …` in the source,
`test_each_degradation_row_drives_its_own_branch` traces execution onto the tag,
and `test_every_degradation_branch_is_driven_by_a_row` fails if the source grows
a branch this table does not reach.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import TypeAlias

import pytest
from _imports import module_imports

from shepherd.core.runner import PaneFields, PaneKind, PaneState
from shepherd.runner import pane as pane_module
from shepherd.runner.pane import (
    DIALOG_FOOTER,
    DecisionPrompt,
    parse_pane_fields,
    read_decision,
    read_pane,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"

#: The `*-fmt.txt` lines recorded beside each capture, in `PANE_FORMAT` order,
#: with the host name redacted exactly as `tests/runner/test_pane.py` redacts it.
PERMISSION_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
TRUST_FIELDS = "0|0||<redacted: host name>|160|45|4041880"
PROMPT_READY_FIELDS = "1|0||✳ Claude Code|160|45|4041880"

#: The naive parser the design doc names as the trap: numbered choices only.
NUMERIC_PARSER = re.compile(r"^\s*(?:❯\s*)?(\d+)\.", re.MULTILINE)

#: The engine's own numbering, stripped back off a choice line to compare the
#: label the parser produced against the line the screen drew.
NUMBER_LABEL = re.compile(r"^\d+\.\s*")

CURSOR_PREFIX = " ❯ "
PLAIN_PREFIX = "   "
RULE_RUN = "────────"


def state_for(capture: str, fields_line: str) -> PaneState:
    return read_pane((RUN / capture).read_bytes(), parse_pane_fields(fields_line))


def permission_state() -> PaneState:
    return state_for("06-permission-dialog.ansi", PERMISSION_FIELDS)


def trust_state() -> PaneState:
    return state_for("01-trust-dialog.ansi", TRUST_FIELDS)


def trust_yes_state() -> PaneState:
    """The same trust screen with the cursor moved to the **last** option."""
    return state_for("01c-trust-yes-selected.txt", TRUST_FIELDS)


def with_dialog_text(state: PaneState, text: str | None) -> PaneState:
    return PaneState(
        kind=state.kind,
        fields=state.fields,
        input_text=state.input_text,
        ghost_text=state.ghost_text,
        dialog_text=text,
    )


def dialog_text_of(state: PaneState) -> str:
    assert state.dialog_text is not None
    return state.dialog_text


def prompt_of(state: PaneState) -> DecisionPrompt:
    prompt = read_decision(state)
    assert prompt is not None
    return prompt


# ----- A8: the assumption this task was allowed to start on -------------------


def test_the_permission_dialogs_numbered_options_reach_dialog_text() -> None:
    """A8, the stop-and-report gate, kept as a standing assertion.

    `read_pane` detects the permission dialog from `PERMISSION_MARKER` *plus* a
    numbered option line, so the lines are on the screen; that they survive into
    `PaneState.dialog_text` was `inferred`, and this is the assertion that turns
    it into a measurement. If `dialog_text` is ever narrowed to the question
    alone, every parser below loses its input and this row says so first.
    """
    state = permission_state()
    assert state.kind is PaneKind.PERMISSION_DIALOG
    assert " ❯ 1. Yes" in dialog_text_of(state)
    assert (
        "   2. Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project"
        in dialog_text_of(state)
    )
    assert "   3. No" in dialog_text_of(state)


# ----- shape 1: the permission dialog -----------------------------------------


def test_the_choices_are_the_engines_own_numbering() -> None:
    """U11: the engine's prompt, numbered the way the TUI numbers it — verbatim.

    Choice 2 carries the *scope* (`always allow … from this project`) and is
    usually the one a person wants. A flattening to approve/reject makes it
    unreachable, so it is asserted here character for character.
    """
    prompt = prompt_of(permission_state())

    assert [choice.number for choice in prompt.choices] == [1, 2, 3]
    assert [choice.label for choice in prompt.choices] == [
        "Yes",
        "Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project",
        "No",
    ]
    assert prompt.kind is PaneKind.PERMISSION_DIALOG
    assert prompt.text.endswith("Do you want to proceed?")
    assert "touch perm-probe.txt" in prompt.text


# ----- shape 2: the trust dialog (C15) ----------------------------------------


def test_the_trust_dialogs_choices_are_unnumbered_and_read_positionally() -> None:
    """The negative control is the naive parser itself, run on the same bytes.

    `NUMERIC_PARSER` is what a `^\\s*❯?\\s*(\\d+)\\.` implementation would find in
    the trust screen: nothing. If "no numbered lines" were read as "not a
    dialog", a blocked session would report no ask while it sat there forever.
    """
    state = trust_state()
    assert NUMERIC_PARSER.search(dialog_text_of(state)) is None

    prompt = prompt_of(state)
    assert [choice.label for choice in prompt.choices] == [
        "No, exit",
        "Yes, I trust this folder",
    ]
    assert [choice.number for choice in prompt.choices] == [None, None]


def test_no_default_is_synthesised_the_cursor_is_reported_where_it_is() -> None:
    """Both captured defaults put `❯` on the **first** choice, and they mean
    opposites.

    That is the whole hazard in one assertion: a caller keyed on position, or on
    "the cursor means yes", answers C15 with *No, exit*. `read_decision` reports
    which line carries the cursor and decides nothing.
    """
    permission = prompt_of(permission_state())
    trust = prompt_of(trust_state())

    assert [choice.selected for choice in permission.choices] == [True, False, False]
    assert [choice.selected for choice in trust.choices] == [True, False]

    assert permission.choices[0].label == "Yes"
    assert trust.choices[0].label == "No, exit"
    assert permission.selected is not None and permission.selected.label == "Yes"
    assert trust.selected is not None and trust.selected.label == "No, exit"


# ----- C1: the block is structural, the cursor only marks a member ------------


def test_the_choice_block_is_not_anchored_on_the_cursor() -> None:
    """`01c`: `❯` on the **last** option, and the first option is still a choice.

    The bug this pins: the block used to start *at* the cursor, so every option
    above it left `choices` and reappeared as the tail of `text`. Here that would
    show up twice over — `No, exit` missing from the list, `No, exit` present in
    the ask — and at this particular boundary it degraded to `None` outright,
    reporting no readable ask for a screen a human reads at a glance.
    """
    prompt = prompt_of(trust_yes_state())

    assert [choice.label for choice in prompt.choices] == [
        "No, exit",
        "Yes, I trust this folder",
    ]
    assert [choice.selected for choice in prompt.choices] == [False, True]
    assert prompt.selected is not None and prompt.selected.label == "Yes, I trust this folder"
    assert "No, exit" not in prompt.text
    assert prompt.text.endswith("Security guide")


def moved_cursor(text: str, lines: tuple[str, ...], to: int) -> str:
    """The same screen with `❯` on a different option — nothing else changed."""
    for index, line in enumerate(lines):
        want = CURSOR_PREFIX if index == to else PLAIN_PREFIX
        moved = want + line[len(CURSOR_PREFIX) :]
        assert line != moved or line.startswith(want)
        text = text.replace(line, moved)
    return text


def test_every_option_survives_wherever_the_cursor_is() -> None:
    """The permission dialog with `❯` walked down all three options.

    One capture records one cursor position; a poll landing mid-interaction, or a
    human attached to the pane, records the others. The list must not change with
    it, and the *selected* member must be the one the cursor is on — asserted
    against the engine's own numbering, which is independent of the parser.
    """
    state = permission_state()
    lines = PERMISSION.choices

    for position in range(len(lines)):
        moved = with_dialog_text(state, moved_cursor(dialog_text_of(state), lines, position))
        prompt = prompt_of(moved)

        assert [choice.number for choice in prompt.choices] == [1, 2, 3]
        assert [choice.selected for choice in prompt.choices] == [
            index == position for index in range(3)
        ]
        assert prompt.selected is not None and prompt.selected.number == position + 1
        assert prompt.text.endswith("Do you want to proceed?")
        assert "1. Yes" not in prompt.text


# ----- E17: this module cannot answer what it reads ---------------------------


PANE_SOURCE = Path(pane_module.__file__)
LOCAL_SOURCE = PANE_SOURCE.with_name("local.py")

#: What a pure reader of bytes is allowed to import: the standard library pieces
#: it parses with, and the two `shepherd.core` vocabularies it returns. Anything
#: imported from one of these is permitted too — the names are module roots, so
#: a new symbol from `shepherd.core.runner` is ordinary work and a new *module*
#: is not.
PURE_IMPORT_ROOTS = (
    "__future__",
    "re",
    "collections.abc",
    "dataclasses",
    "shepherd.core.anomalies",
    "shepherd.core.runner",
)


def test_the_trust_dialog_is_named_so_a_caller_can_refuse_it_by_name() -> None:
    """E17, half one. The prompt carries `PaneKind.TRUST_DIALOG`, so a caller can
    refuse this one screen by name rather than by guessing at its text. The
    control is the permission dialog, named `PERMISSION_DIALOG` — proving the
    naming is a discrimination and not a constant."""
    assert prompt_of(trust_state()).kind is PaneKind.TRUST_DIALOG
    assert prompt_of(trust_yes_state()).kind is PaneKind.TRUST_DIALOG
    assert prompt_of(permission_state()).kind is PaneKind.PERMISSION_DIALOG


def test_pane_holds_no_runner_handle_and_no_transport() -> None:
    """E17, half two — asserted on the **import surface**, not on names.

    A blind Enter on the trust screen answers *"No, exit"*, so the module that
    reads that screen must be unable to send one. The previous form of this test
    searched `dir(pane)` for `answer|send|press|key|enter|confirm` and was
    green — while the verb that actually sends keystrokes in this repo is
    `LocalRunner.write` (`runner/local.py`, `send-keys -H`), which matches none
    of those words, and `clear_input` and `interrupt` sit beside it. A name regex
    over a vocabulary it does not know is not a gate, and that one had no control
    proving it could ever be non-empty.

    What is actually true, and checkable, is that `pane.py` imports no runner, no
    transport and no process: its whole import surface is `re`, `dataclasses`,
    `collections.abc` and `shepherd.core.*`. A `write`, `respond`, `submit`,
    `choose` or `deliver` added here would need one of the three, whatever it
    were called.

    **The control is `local.py`**, the module that does hold the handle: the same
    predicate run over it is non-empty and names `subprocess`. Without it this
    assertion could be green because the walker returned nothing.

    The walker is `tests/boundaries/_imports.module_imports`, the tree's one
    import scanner, used **inside** this test rather than wrapped in a helper:
    a sixth copy of that walk is the duplication `test_one_definition_site.py`
    exists to catch.
    """

    def outside_the_pure_surface(path: Path) -> set[str]:
        return {
            name
            for name in module_imports(path)
            if not any(name == root or name.startswith(f"{root}.") for root in PURE_IMPORT_ROOTS)
        }

    assert outside_the_pure_surface(PANE_SOURCE) == set()

    transport = outside_the_pure_surface(LOCAL_SOURCE)
    assert "subprocess" in transport, sorted(transport)


# ----- E16: degrade, never guess ----------------------------------------------


@dataclass(frozen=True)
class Shape:
    """One captured dialog, plus the choice lines it draws, **verbatim**.

    `choices` is in screen order and `cursor` is the index of the one the capture
    marks, so a mutilation can be written once and applied to every shape — the
    permission dialog and *both* trust states, rather than the permission dialog
    alone, which is how one shape of two came to be certified.
    """

    name: str
    state: Callable[[], PaneState]
    choices: tuple[str, ...]
    cursor: int

    @property
    def cursor_line(self) -> str:
        return self.choices[self.cursor]

    @property
    def below_cursor(self) -> str | None:
        after = self.choices[self.cursor + 1 :]
        return after[0] if after else None

    @property
    def other_line(self) -> str:
        other = [line for index, line in enumerate(self.choices) if index != self.cursor]
        return other[0]


PERMISSION = Shape(
    name="permission",
    state=permission_state,
    choices=(
        " ❯ 1. Yes",
        "   2. Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project",
        "   3. No",
    ),
    cursor=0,
)
TRUST = Shape(
    name="trust (cursor on the first option)",
    state=trust_state,
    choices=(" ❯ No, exit", "   Yes, I trust this folder"),
    cursor=0,
)
TRUST_YES = Shape(
    name="trust (cursor on the last option)",
    state=trust_yes_state,
    choices=("   No, exit", " ❯ Yes, I trust this folder"),
    cursor=1,
)
SHAPES = (PERMISSION, TRUST, TRUST_YES)


def test_every_shapes_choice_lines_are_the_ones_on_the_screen() -> None:
    """The table above is transcribed from three captures; this is the row that
    says so. Every mutilation below is keyed on these literals, so a typo in one
    would make a mutilation a no-op and its row green for the wrong reason."""
    for shape in SHAPES:
        text = dialog_text_of(shape.state())
        for line in shape.choices:
            assert f"\n{line}\n" in text, (shape.name, line)
        assert shape.cursor_line.startswith(CURSOR_PREFIX)
        parsed = prompt_of(shape.state()).choices
        assert [choice.label for choice in parsed] == [
            NUMBER_LABEL.sub("", line[len(CURSOR_PREFIX) :]).strip() for line in shape.choices
        ]
        assert [choice.selected for choice in parsed] == [
            index == shape.cursor for index in range(len(shape.choices))
        ]


def without_line(text: str, needle: str) -> str:
    kept = [line for line in text.split("\n") if needle not in line]
    assert len(kept) < len(text.split("\n")), f"{needle!r} was not in the capture"
    return "\n".join(kept)


def drop_footer(shape: Shape, text: str) -> str:
    return without_line(text, DIALOG_FOOTER)


def drop_rule(shape: Shape, text: str) -> str:
    return without_line(text, RULE_RUN)


def drop_cursor_line(shape: Shape, text: str) -> str:
    """The cursor gone from the box. The permission capture's scrollback still
    holds the operator's own `❯ Use the Bash tool …` line, well above the rule —
    which is exactly what used to make this row trip the alignment branch."""
    return without_line(text, shape.cursor_line)


def dedent_below_cursor(shape: Shape, text: str) -> str:
    """One choice line under the cursor dedented to column 0: the block stops
    before the footer, so the list is not the list we think it is."""
    assert shape.below_cursor is not None
    out = text.replace(shape.below_cursor, shape.below_cursor.strip())
    assert out != text
    return out


def add_second_cursor(shape: Shape, text: str) -> str:
    marked = CURSOR_PREFIX + shape.other_line[len(PLAIN_PREFIX) :]
    out = text.replace(shape.other_line, marked)
    assert out != text
    return out


def keep_only_the_selected_choice(shape: Shape, text: str) -> str:
    """Every option but the marked one removed. On `01c` this leaves a screen
    whose single choice is *"Yes, I trust this folder"* — C15 through the front
    door, and the only thing standing in its way is `_MINIMUM_CHOICES`."""
    for line in shape.choices:
        if line != shape.cursor_line:
            text = without_line(text, line)
    return text


def remove_the_ask(shape: Shape, text: str) -> str:
    """Everything between the box rule and the first choice, gone: a choice list
    in a box with no question above it."""
    lines = text.split("\n")
    first = next(index for index, line in enumerate(lines) if line == shape.choices[0])
    rule = max(index for index in range(first) if RULE_RUN in lines[index])
    assert rule + 1 < first
    return "\n".join(lines[: rule + 1] + lines[first:])


@dataclass(frozen=True)
class Row:
    """One mutilation, and the **one** branch it is supposed to drive."""

    name: str
    mutilate: Callable[[Shape, str], str]
    branch: str
    shapes: tuple[Shape, ...] = SHAPES


ROWS: tuple[Row, ...] = (
    Row("the footer is gone", drop_footer, "no footer"),
    Row("the box rule is gone", drop_rule, "no rule"),
    Row("the cursor line is gone", drop_cursor_line, "no cursor in the box"),
    Row(
        "a choice is dedented out of the block",
        dedent_below_cursor,
        "the block does not reach the footer",
        shapes=(PERMISSION, TRUST),
    ),
    Row("a second line carries the cursor", add_second_cursor, "a second cursor"),
    Row(
        "only the selected choice is left",
        keep_only_the_selected_choice,
        "below the two-choice floor",
    ),
    Row("the ask above the block is gone", remove_the_ask, "no ask above the block"),
)

CASES = [(row, shape) for row in ROWS for shape in row.shapes]
CASE_IDS = [f"{row.name} · {shape.name}" for row, shape in CASES]


@pytest.mark.parametrize(("row", "shape"), CASES, ids=CASE_IDS)
def test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses(
    row: Row, shape: Shape
) -> None:
    """E16. Each row asserts the *unmutilated* capture parses first, so a row
    cannot go green because the parser stopped working altogether."""
    state = shape.state()
    assert read_decision(state) is not None, f"control for {row.name!r} is already None"

    mutilated = with_dialog_text(state, row.mutilate(shape, dialog_text_of(state)))
    assert read_decision(mutilated) is None


# ----- E16, the part the first version of this file got wrong -----------------

_DEGRADE = re.compile(r"return None  # degrade: (?P<tag>.+)$")

#: What `sys.settrace` hands back and takes: the local trace function for one
#: frame, which returns itself to keep receiving that frame's line events.
Tracer: TypeAlias = Callable[[FrameType, str, object], "Tracer | None"]


def degrade_branches() -> dict[str, int]:
    """Every tagged `return None` in `read_decision`, by line number."""
    found: dict[str, int] = {}
    for number, line in enumerate(PANE_SOURCE.read_text(encoding="utf-8").split("\n"), start=1):
        match = _DEGRADE.search(line)
        if match is not None:
            tag = match.group("tag")
            assert tag not in found, f"two branches tagged {tag!r}"
            found[tag] = number
    return found


def branch_taken(state: PaneState) -> str | None:
    """Which tagged branch `read_decision` actually returned through.

    `sys.settrace` on the one frame, rather than a reason string on the return
    value: the interface stays `DecisionPrompt | None` — a caller must not be
    able to route on *why* a screen was unreadable, because every reason means
    the same thing to it — while the test still sees the line that ran.
    """
    tags = {number: tag for tag, number in degrade_branches().items()}
    fired: list[str] = []

    def tracer(frame: FrameType, event: str, arg: object) -> Tracer | None:
        if frame.f_code is not read_decision.__code__:
            return None
        if event == "line" and frame.f_lineno in tags:
            fired.append(tags[frame.f_lineno])
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        result = read_decision(state)
    finally:
        sys.settrace(previous)

    assert len(fired) <= 1, fired
    assert (result is None) == bool(fired), (result, fired)
    return fired[0] if fired else None


@pytest.mark.parametrize(("row", "shape"), CASES, ids=CASE_IDS)
def test_each_degradation_row_drives_its_own_branch(row: Row, shape: Shape) -> None:
    """The assertion the four-row table above never made.

    Traced, the original four rows trod **three** branches: the footer row and
    the rule row hit theirs, and *both* the cursor row and the alignment row hit
    the alignment one — the cursor-absent branch was never executed by any test
    in the suite, while the table read as if it were. A row here is green only
    if it returns through the branch it names."""
    state = shape.state()
    assert branch_taken(state) is None, f"control for {row.name!r} is already degrading"

    mutilated = with_dialog_text(state, row.mutilate(shape, dialog_text_of(state)))
    assert branch_taken(mutilated) == row.branch


def test_a_pane_that_is_asking_nothing_returns_through_the_first_branch() -> None:
    """The eighth branch: the kind gate, which is not a mutilation of a dialog."""
    idle = state_for("03-after-stop.ansi", PROMPT_READY_FIELDS)
    assert idle.kind is PaneKind.PROMPT_READY
    assert branch_taken(idle) == "not a dialog"
    assert branch_taken(with_dialog_text(permission_state(), None)) == "not a dialog"
    assert branch_taken(with_dialog_text(permission_state(), "")) == "not a dialog"


def test_every_degradation_branch_is_driven_by_a_row() -> None:
    """The population gate. A `return None` added to `read_decision` without a
    row here is a degradation nothing has ever observed — which is how three of
    the eight came to be uncovered while four rows claimed otherwise."""
    driven = {row.branch for row in ROWS} | {"not a dialog"}
    assert set(degrade_branches()) == driven


# ----- the floor, which is the only thing standing between C15 and a card -----


def test_a_single_aligned_line_is_not_a_choice_list() -> None:
    """`_MINIMUM_CHOICES` pinned, on the capture where the mutant is dangerous.

    With the floor at 1, `01c` minus its `No, exit` line renders as a one-choice
    card whose only choice is **"Yes, I trust this folder"**: the refusal is off
    the screen, and a card that offers one button is a card that gets pressed.
    That is C15 arriving through the front door, and until this row existed the
    constant could be changed to 1 with all 17 tests still green.

    The floor is asserted as a *number* as well, because the row above only bites
    at 1: at 3 the permission dialog would still parse and both trust shapes
    would degrade, which no other assertion in this file would notice.
    """
    assert pane_module._MINIMUM_CHOICES == 2

    state = trust_yes_state()
    one_choice = keep_only_the_selected_choice(TRUST_YES, dialog_text_of(state))
    assert "Yes, I trust this folder" in one_choice
    assert "No, exit" not in one_choice

    assert read_decision(with_dialog_text(state, one_choice)) is None
    assert branch_taken(with_dialog_text(state, one_choice)) == "below the two-choice floor"


# ----- totality ----------------------------------------------------------------


def test_an_empty_or_absent_dialog_text_is_not_a_decision() -> None:
    state = permission_state()
    assert read_decision(with_dialog_text(state, None)) is None
    assert read_decision(with_dialog_text(state, "")) is None


@pytest.mark.parametrize("shape", SHAPES, ids=[shape.name for shape in SHAPES])
def test_read_decision_never_raises_for_any_prefix_of_a_real_capture(shape: Shape) -> None:
    """Degradation is total: every truncation of a captured dialog either parses
    or returns `None`, and none of them raises. A prefix is the shape a poll
    landing mid-redraw actually sees."""
    text = dialog_text_of(shape.state())
    lines = text.split("\n")

    for cut in range(len(lines) + 1):
        read_decision(with_dialog_text(shape.state(), "\n".join(lines[:cut])))


# ----- everything that is not a dialog ----------------------------------------


@pytest.mark.parametrize(
    ("capture", "fields_line", "expected"),
    (
        ("02-after-trust.ansi", PROMPT_READY_FIELDS, PaneKind.PROMPT_READY),
        ("03-after-stop.ansi", PROMPT_READY_FIELDS, PaneKind.PROMPT_READY),
        ("08-prompt-with-suggestion.ansi", PROMPT_READY_FIELDS, PaneKind.PROMPT_READY),
    ),
)
def test_a_pane_that_is_not_a_dialog_has_no_decision(
    capture: str, fields_line: str, expected: PaneKind
) -> None:
    """An idle, prompt-ready session is asking nothing — and its screen still
    carries `❯` lines, which is exactly what would fool a cursor-keyed parser
    that did not check the kind first."""
    state = state_for(capture, fields_line)
    assert state.kind is expected
    assert read_decision(state) is None


def test_a_dead_pane_has_no_decision() -> None:
    dead = PaneState(
        kind=PaneKind.DEAD,
        fields=parse_pane_fields("0|1|143||160|45|4042531"),
        input_text="",
        ghost_text=None,
        dialog_text=None,
    )
    assert read_decision(dead) is None


def test_the_kinds_that_carry_a_dialog_are_the_kinds_that_can_be_asked() -> None:
    """One constant, referenced twice. `_state` populates `dialog_text` for
    `DIALOG_KINDS` and `read_decision` gates on the same tuple; two copies drift,
    and the drift is silent — a populated `dialog_text` that `read_decision`
    answers `None` for is a session with a visible ask reporting no ask."""
    assert pane_module.DIALOG_KINDS == (PaneKind.TRUST_DIALOG, PaneKind.PERMISSION_DIALOG)

    for kind in PaneKind:
        state = state_for("06-permission-dialog.ansi", PERMISSION_FIELDS)
        moved = PaneState(
            kind=kind,
            fields=state.fields,
            input_text=state.input_text,
            ghost_text=state.ghost_text,
            dialog_text=state.dialog_text,
        )
        assert (read_decision(moved) is not None) == (kind in pane_module.DIALOG_KINDS)


def test_read_decision_leaves_its_input_alone() -> None:
    """Pure: same state in, equal prompt out, and the state is unchanged."""
    state = permission_state()
    before = (state.kind, state.dialog_text, state.input_text)
    first, second = read_decision(state), read_decision(state)
    assert first == second
    assert (state.kind, state.dialog_text, state.input_text) == before


def test_fields_are_not_consulted() -> None:
    """The decision is read off the screen, not off tmux's format fields: the
    same `dialog_text` under different fields yields the same prompt."""
    state = permission_state()
    other: PaneFields = parse_pane_fields("0|0||other|70|30|1234")
    moved = PaneState(
        kind=state.kind,
        fields=other,
        input_text=state.input_text,
        ghost_text=state.ghost_text,
        dialog_text=state.dialog_text,
    )
    assert read_decision(moved) == read_decision(state)
