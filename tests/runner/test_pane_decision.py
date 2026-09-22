"""T8.1: the decision the screen is asking for, read off a `PaneState`.

**Read by path out of `docs/probes/`, never from a fixture copy.** The two shapes
this parser has to survive are `run-20260914T154946Z/06-permission-dialog.ansi`
and `run-20260914T154946Z/01-trust-dialog.ansi`, and they disagree about the one
thing that matters: in the permission dialog `❯` sits on *Yes*, in the trust
dialog it sits on *No, exit*. A parser that reads the cursor as "the safe
default" answers C15's trust dialog by exiting the session.

**Every degradation here has a negative control, and each control names the
single branch it exercises.** Phase 0 shipped a checker whose one control
certified one of five gates; the other four were holes. So `E16`'s table below
mutilates the *real* capture one structural element at a time — footer, cursor,
box rule, alignment — and each row asserts the unmutilated text parses, so a row
that goes green because the parser stopped working at all is red instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shepherd.core.runner import PaneFields, PaneKind, PaneState
from shepherd.runner import pane as pane_module
from shepherd.runner.pane import DecisionPrompt, parse_pane_fields, read_decision, read_pane

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"

#: The `*-fmt.txt` lines recorded beside each capture, in `PANE_FORMAT` order,
#: with the host name redacted exactly as `tests/runner/test_pane.py` redacts it.
PERMISSION_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
TRUST_FIELDS = "0|0||<redacted: host name>|160|45|4041880"
PROMPT_READY_FIELDS = "1|0||✳ Claude Code|160|45|4041880"

#: The naive parser the design doc names as the trap: numbered choices only.
NUMERIC_PARSER = re.compile(r"^\s*(?:❯\s*)?(\d+)\.", re.MULTILINE)


def state_for(capture: str, fields_line: str) -> PaneState:
    return read_pane((RUN / capture).read_bytes(), parse_pane_fields(fields_line))


def permission_state() -> PaneState:
    return state_for("06-permission-dialog.ansi", PERMISSION_FIELDS)


def trust_state() -> PaneState:
    return state_for("01-trust-dialog.ansi", TRUST_FIELDS)


def with_dialog_text(state: PaneState, text: str | None) -> PaneState:
    return PaneState(
        kind=state.kind,
        fields=state.fields,
        input_text=state.input_text,
        ghost_text=state.ghost_text,
        dialog_text=text,
    )


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
    assert state.dialog_text is not None
    assert " ❯ 1. Yes" in state.dialog_text
    assert (
        "   2. Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project"
        in state.dialog_text
    )
    assert "   3. No" in state.dialog_text


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
    assert state.dialog_text is not None
    assert NUMERIC_PARSER.search(state.dialog_text) is None

    prompt = prompt_of(state)
    assert [choice.label for choice in prompt.choices] == [
        "No, exit",
        "Yes, I trust this folder",
    ]
    assert [choice.number for choice in prompt.choices] == [None, None]


def test_the_trust_dialog_is_named_and_never_answered_blind() -> None:
    """E17, and it has two halves — this test exercises both, separately.

    **Half one, naming.** The prompt carries `PaneKind.TRUST_DIALOG`, so a caller
    can refuse this one screen by name rather than by guessing at its text.

    **Half two, no answering verb at this seam.** `pane.py` is a pure reader; a
    blind Enter on this screen answers *"No, exit"*, so the module that reads it
    exports nothing that could send one. The control for this half is the
    permission dialog, which is named `PERMISSION_DIALOG` — proving the naming is
    a discrimination and not a constant.
    """
    prompt = prompt_of(trust_state())
    assert prompt.kind is PaneKind.TRUST_DIALOG
    assert prompt_of(permission_state()).kind is PaneKind.PERMISSION_DIALOG

    answering = [
        name
        for name in dir(pane_module)
        if not name.startswith("__")
        and re.search(r"answer|send|press|key|enter|confirm", name, re.IGNORECASE)
    ]
    assert answering == [], answering


def test_no_default_is_synthesised_the_cursor_is_reported_where_it_is() -> None:
    """Both shapes put `❯` on the **first** choice, and they mean opposites.

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


# ----- E16: degrade, never guess ----------------------------------------------


def without_line(text: str, needle: str) -> str:
    kept = [line for line in text.split("\n") if needle not in line]
    assert len(kept) < len(text.split("\n")), f"{needle!r} was not in the capture"
    return "\n".join(kept)


def break_alignment(text: str) -> str:
    """One choice line dedented to column 0: the block stops being a block."""
    out = text.replace("   3. No", "3. No")
    assert out != text
    return out


#: One row per structural element the parser depends on. **Each row names the
#: single branch it exercises** — Phase 0's lesson, applied: a table of four
#: mutilations that all happened to trip the same early return would certify one
#: branch while reading as four.
MUTILATIONS: tuple[tuple[str, str], ...] = (
    ("the footer is gone", "Esc to cancel"),
    ("the cursor line is gone", "❯ 1. Yes"),
    ("the box rule is gone", "────────"),
)


@pytest.mark.parametrize(("branch", "needle"), MUTILATIONS, ids=[row[0] for row in MUTILATIONS])
def test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses(
    branch: str, needle: str
) -> None:
    """E16. Each row asserts the *unmutilated* text parses first, so a row cannot
    go green because the parser stopped working altogether."""
    state = permission_state()
    assert state.dialog_text is not None
    assert read_decision(state) is not None, f"control for {branch!r} is already None"

    mutilated = with_dialog_text(state, without_line(state.dialog_text, needle))
    assert read_decision(mutilated) is None


def test_a_misaligned_choice_block_degrades_the_fourth_branch() -> None:
    """The fourth branch, kept separate because it mutilates rather than deletes:
    a choice dedented out of the block is not a choice list we can read."""
    state = permission_state()
    assert state.dialog_text is not None
    assert read_decision(state) is not None

    assert read_decision(with_dialog_text(state, break_alignment(state.dialog_text))) is None


def test_an_empty_or_absent_dialog_text_is_not_a_decision() -> None:
    state = permission_state()
    assert read_decision(with_dialog_text(state, None)) is None
    assert read_decision(with_dialog_text(state, "")) is None


def test_read_decision_never_raises_for_any_prefix_of_a_real_capture() -> None:
    """Degradation is total: every truncation of the permission screen either
    parses or returns `None`, and none of them raises. The population is asserted
    so the loop cannot silently shrink."""
    state = permission_state()
    assert state.dialog_text is not None
    lines = state.dialog_text.split("\n")
    assert len(lines) > 40

    seen = 0
    for cut in range(len(lines) + 1):
        result = read_decision(with_dialog_text(state, "\n".join(lines[:cut])))
        assert result is None or isinstance(result, DecisionPrompt)
        seen += 1
    assert seen == len(lines) + 1


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
