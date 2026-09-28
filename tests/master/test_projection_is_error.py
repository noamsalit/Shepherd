"""qa6 P5 / BC-07 — a result the engine marks `is_error` ends the turn as an error.

**The defect.** `result_ending()` read the subtype and the terminal reason and
never `ResultMessage.is_error`, so an engine-side API failure — `subtype:
"success"`, `terminal_reason: "api_error"`, `is_error: true` — became
`turn_ended` with `outcome="unknown"`, and the chat page drew a failed turn as
one that finished (report §8, L11).

**Two seams.** The unit seam is `result_ending` itself, with expectations written
as literals from the plan's own examples. The wiring seam is `project_events`
over a line the vendor's parser read, so a `result_ending` that learned the flag
while `project_events` never passed it would still go red here.
"""

from __future__ import annotations

from shepherd.core.anomalies import AnomalyKind
from shepherd.master import projection

from . import tape


def test_an_is_error_result_is_an_error_ending() -> None:
    """The report's own ending: a `success` subtype the engine flagged as failed."""
    assert projection.result_ending("success", "api_error", True) == ("error", "error", True)


def test_a_clean_result_is_unchanged() -> None:
    assert projection.result_ending("success", "completed", False) == (
        "turn_ended",
        "success",
        False,
    )


def test_a_flagged_error_subtype_keeps_its_own_outcome() -> None:
    """P2's ending (`error_during_execution` / `aborted_tools`, `is_error` true)
    already names its failure; the flag must not flatten it to `"error"`."""
    assert projection.result_ending("error_during_execution", "aborted_tools", True) == (
        "error",
        "error_during_execution",
        False,
    )


def test_a_projected_is_error_result_is_an_error_and_is_counted() -> None:
    """Through the vendor's parser and `project_events`: the flag reaches the
    ending, and the unrecognised `api_error` reason still moves the counter."""
    from claude_agent_sdk._internal.message_parser import parse_message

    line = {**tape.result_line(terminal_reason="api_error"), "is_error": True}
    counted: list[AnomalyKind] = []
    events = projection.project_events(
        parse_message(line), bump=counted.append, tool_names={}
    )

    assert [event.kind for event in events] == ["error"]
    assert events[0].payload[projection.OUTCOME_KEY] == "error"
    assert events[0].kind in projection.TERMINAL_KINDS
    assert counted == [AnomalyKind.MASTER_RESULT_UNMAPPED], counted
