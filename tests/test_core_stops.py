"""T1 — `core/stops.py`, the stop vocabulary every M2 package speaks in.

Types only: a failure here is a vocabulary that two packages would otherwise
each define their own copy of (F9 / BLOCKER-T7b-1). The bucket *map* and the
action *table* are T7's; this module holds what they must be total over.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from shepherd.core import stops

SOURCE = Path(stops.__file__)

#: ADR-M2-3: `TurnEnding` is a **narrowing**, not a rename. No member *value*
#: may be one of the engine's own four observed `message.stop_reason` spellings.
ENGINE_ENDING_SPELLINGS = frozenset({"end_turn", "tool_use", "max_tokens", "stop_sequence"})


def test_stop_reason_has_twenty_members() -> None:
    """16 mechanical + 4 completeness, spelled as migration 002's CHECK lists them."""
    members = list(stops.StopReason)
    assert len(members) == 20
    assert {member.value for member in members} == {
        "rate_limited",
        "quota_paused",
        "auth_failed",
        "account_blocked",
        "bad_request",
        "server_error",
        "truncated",
        "stalled_pending_tool",
        "crashed",
        "killed",
        "context_exhausted",
        "user_exited",
        "cleared",
        "logged_out",
        "resumed_elsewhere",
        "unknown",
        "completed",
        "incomplete",
        "derailed",
        "blocked_external",
    }


def test_stop_reason_cleared_is_not_the_fold_clear_sentinel() -> None:
    """Different namespaces; a module needing both imports the module, not the name."""
    from shepherd.core.fold_types import CLEARED

    assert stops.StopReason.CLEARED.value == "cleared"
    assert CLEARED == ""
    assert stops.StopReason.CLEARED != CLEARED


def test_every_bucket_has_a_colour_and_a_glyph() -> None:
    """§4 verbatim for seven, plus `unclassified` (D-4). Colour *and* glyph, so
    amber/red survive colourblindness and greyscale."""
    assert len(list(stops.Bucket)) == 8
    assert set(stops.PALETTE) == set(stops.Bucket)
    for bucket, style in stops.PALETTE.items():
        assert style.colour.startswith("#") and len(style.colour) == 7, bucket
        assert style.glyph, bucket
        assert style.label, bucket
        assert style.who_acts, bucket
    colours = [style.colour for style in stops.PALETTE.values()]
    assert len(set(colours)) == 8
    glyphs = [style.glyph for style in stops.PALETTE.values()]
    assert len(set(glyphs)) == 8
    # §4's own values, not recomputed — the spec's table, line 202-208.
    assert stops.PALETTE[stops.Bucket.RUNNING].colour == "#3B82F6"
    assert stops.PALETTE[stops.Bucket.NEEDS_YOU].glyph == "⏸"
    assert stops.PALETTE[stops.Bucket.ERROR].colour == "#EF4444"
    assert stops.PALETTE[stops.Bucket.UNCLASSIFIED].colour == "#9CA3AF"
    assert stops.PALETTE[stops.Bucket.UNCLASSIFIED].glyph == "?"


def test_bucket_order_is_total_over_bucket() -> None:
    assert len(stops.BUCKET_ORDER) == 8
    assert set(stops.BUCKET_ORDER) == set(stops.Bucket)
    assert len(set(stops.BUCKET_ORDER)) == 8
    assert stops.BUCKET_ORDER[0] is stops.Bucket.NEEDS_YOU
    # A row we could not classify never outranks one we could.
    assert stops.BUCKET_ORDER[-1] is stops.Bucket.UNCLASSIFIED


def test_blocked_sorts_below_running() -> None:
    """§12, deliberately: it is real, it is visible, it is not yours to act on."""
    order = list(stops.BUCKET_ORDER)
    assert order.index(stops.Bucket.BLOCKED) > order.index(stops.Bucket.RUNNING)


def test_turn_ending_has_five_members_and_no_engine_spelling() -> None:
    """ADR-M2-3's narrowing, checked as a property rather than trusted."""
    members = list(stops.TurnEnding)
    assert len(members) == 5
    assert {member.name for member in members} == {
        "ENDED_TURN",
        "HELD_TOOL_CALL",
        "HIT_TOKEN_CAP",
        "OTHER",
        "ABSENT",
    }
    for member in members:
        assert member.value not in ENGINE_ENDING_SPELLINGS, member.name
    # …and the assertion is about the *source*, not only the runtime values: an
    # engine spelling must not appear as a literal in the module at all.
    literals = {
        node.value
        for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert literals & ENGINE_ENDING_SPELLINGS == set()


def test_decided_by_has_five_members() -> None:
    """DP1 — `heuristic` exists because a heuristic verdict has to say so."""
    assert {member.value for member in stops.DecidedBy} == {
        "mechanical",
        "heuristic",
        "model",
        "declared",
        "manual",
    }


def test_next_action_kind_has_nine_members_and_source_ranks_three() -> None:
    assert len(list(stops.NextActionKind)) == 9
    assert {member.value for member in stops.ActionSource} == {
        "declared",
        "llm",
        "heuristic",
    }


def test_stop_evidence_has_no_mapping_field() -> None:
    """P-M2-6: a mapping field is what K12 fails closed on, and it has no
    totality a test can check. Every field is named and typed."""
    for record in (stops.StopEvidence, stops.TranscriptTail, stops.Verdict):
        for field in dataclasses.fields(record):
            annotation = str(field.type)
            assert "Mapping" not in annotation, f"{record.__name__}.{field.name}"
            assert "dict" not in annotation, f"{record.__name__}.{field.name}"
        assert record.__dataclass_params__.frozen, record.__name__


def test_stop_evidence_field_names_are_neutral() -> None:
    """No field is an engine spelling — the record crosses into `signals/`."""
    names = {field.name for field in dataclasses.fields(stops.StopEvidence)}
    assert names & {"stop_reason", "error", "reason", "source", "hook_event_name"} == set()
    assert "mechanical" in names and "tail" in names


def test_next_action_text_is_capped() -> None:
    """E-M2-28: a column that silently exceeds its documented width is a lie."""
    assert stops.ACTION_TEXT_MAX == 80
    assert stops.MAX_ACTIONS == 3
    action = stops.NextAction(
        text="x" * 200,
        kind=stops.NextActionKind.RETRY,
        target=None,
        source=stops.ActionSource.HEURISTIC,
    )
    assert len(action.text) == stops.ACTION_TEXT_MAX
    assert action.text.endswith("…")


def test_verdict_why_is_capped() -> None:
    assert stops.WHY_MAX == 120
    verdict = stops.Verdict(
        stop_reason=stops.StopReason.UNKNOWN,
        bucket=stops.Bucket.UNCLASSIFIED,
        why="y" * 400,
        confidence=0.0,
        decided_by=stops.DecidedBy.MECHANICAL,
        next_actions=(),
        waiting_on=None,
        missing=(),
    )
    assert len(verdict.why) == stops.WHY_MAX
    assert verdict.why.endswith("…")


def test_short_text_is_not_truncated() -> None:
    """The cap is a boundary, not a transformation applied to everything."""
    action = stops.NextAction(
        text="Review the diff",
        kind=stops.NextActionKind.INSPECT,
        target=None,
        source=stops.ActionSource.HEURISTIC,
    )
    assert action.text == "Review the diff"


def test_the_two_confidence_constants_straddle_the_threshold() -> None:
    """ADR-M2-5: a clean heuristic stop still carries an action, deliberately."""
    assert stops.CONFIDENT_ENOUGH == 0.8
    assert stops.HEURISTIC_COMPLETED_CONFIDENCE == 0.5
    assert stops.HEURISTIC_COMPLETED_CONFIDENCE < stops.CONFIDENT_ENOUGH
    assert stops.STOP_RECORD_VERSION == 1


def test_module_imports_nothing_above_l1_and_has_no_logic() -> None:
    """Inherited `test_core_purity` in property form, plus T1's "no logic" rule."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    for module in imported:
        assert not module.startswith("shepherd.signals"), module
        assert not module.startswith("shepherd.engines"), module
        assert not module.startswith("shepherd.toolsurface"), module
    # No `Classifier` protocol (D34), no model id, no client (P-M2-11).
    # Declarations, not prose: the docstring is allowed to name the thing it
    # forbids, exactly as `test_no_engine_vocabulary_in_signals` allows prose.
    declared = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    assert "Classifier" not in declared
    assert not any(module.startswith("anthropic") for module in imported)
    source = SOURCE.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 300
