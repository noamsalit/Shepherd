"""`classify()` and D34's one named call site (T9, `signals/verdict.py`).

The composition is four lines and the *absences* are the design: no
`Classifier` protocol, no model id, no credential lookup, no prompt, no second
call site. Building the deferred lane means filling one function in and nothing
else in the system moves — which is a property, so it is tested like one.
"""

from __future__ import annotations

import ast
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest
from shepherd.core.stops import (
    BUCKET_ORDER,
    CONFIDENT_ENOUGH,
    WHY_MAX,
    Bucket,
    DecidedBy,
    StopEvidence,
    StopReason,
    ToolFailure,
    ToolUseRef,
    TranscriptTail,
    TurnEnding,
    Verdict,
)
from shepherd.signals import verdict as verdict_module
from shepherd.signals.heuristics import split_completeness
from shepherd.signals.stop_rules import BUCKET_OF
from shepherd.signals.verdict import classify, classify_end_turn

from signals.test_heuristics import evidence, tail  # the shared record builders

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: The frozen capture corpus. A literal that **names a file that really exists**
#: under here is evidence, not a model id — see `names_a_real_capture`.
PROBE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "probes"

#: Anything that looks like a model identifier. The point is not to ban a
#: spelling but to ban the *shape*, so a new model name is caught too.
MODEL_ID = re.compile(r"claude-[a-z0-9.\-]*\d|gpt-[0-9]|sonnet-|opus-|haiku-")

#: The two ways a credential would enter: a named key, or a vault lookup.
CREDENTIAL_WORDS = ("api_key", "apikey", "ANTHROPIC_API_KEY", "bearer ")


def names_a_real_capture(literal: str) -> bool:
    """Is this literal the path of a capture that is actually on disk?

    T13-3: the capture directory `gap-fill/keys-claude-20260914T180105Z/` matches
    `MODEL_ID` — a real probe folder, named after the model that produced it, so
    citing one's path as evidence trips a rule about model *ids*. The narrow fix
    is not to loosen the shape (which is the whole point of the rule) and not to
    exempt a spelling (ADR-1: an exemption is how boundaries die), but to ask the
    filesystem: a literal that resolves to a path which **exists** under
    `docs/probes/` is a citation. A made-up path that merely looks like one still
    trips, which `test_an_invented_capture_path_is_still_caught` pins.
    """
    stripped = literal.strip().lstrip("/")
    if not stripped or "\n" in stripped:
        return False
    candidate = PROBE_ROOT / stripped
    if candidate.exists():
        return True
    return any((PROBE_ROOT / probe / stripped).exists() for probe in PROBE_DIRS)


#: Resolved once: the probe suites a citation may be written relative to.
PROBE_DIRS = tuple(child.name for child in PROBE_ROOT.iterdir() if child.is_dir())


def sources() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def literals(tree: ast.Module) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


# ----- the composition --------------------------------------------------------


def test_confidence_is_one_for_mechanical_reasons() -> None:
    """§8: "mechanical, confidence 1.0" — for a reason a row actually claimed."""
    for reason in StopReason:
        if reason is StopReason.UNKNOWN:
            continue
        given = classify(evidence(mechanical=reason, mechanical_detail="the engine said so"))
        assert given.stop_reason is reason
        assert given.confidence == 1.0
        assert given.decided_by is DecidedBy.MECHANICAL
        assert given.bucket is BUCKET_OF[reason]


def test_the_unknown_residue_never_claims_confidence() -> None:
    """`unknown` is the mechanical table's residue (ADR-M2-5): the row is
    `decided_by = mechanical` because a *rule* wrote it, and its confidence is
    **0.0**, because 1.0 on an answer that says "we could not tell" is the one
    number a tuning backlog must never read as settled."""
    residue = classify(evidence(mechanical=StopReason.UNKNOWN, mechanical_detail="no row"))
    assert residue.stop_reason is StopReason.UNKNOWN
    assert residue.decided_by is DecidedBy.MECHANICAL
    assert residue.confidence == 0.0
    assert residue.bucket is Bucket.ERROR


def test_mechanical_short_circuits_the_split(monkeypatch: pytest.MonkeyPatch) -> None:
    """§8: "that short-circuit is what keeps the common case free."."""

    def explode(_: StopEvidence) -> None:
        raise AssertionError("the split ran on a record the adapter already decided")

    monkeypatch.setattr(verdict_module, "split_completeness", explode)
    decided = classify(
        evidence(
            mechanical=StopReason.RATE_LIMITED,
            mechanical_detail="the engine reported 'rate_limit'",
            tail=tail(ending=TurnEnding.ENDED_TURN),
        )
    )
    assert decided.stop_reason is StopReason.RATE_LIMITED


def test_decided_by_is_heuristic_for_the_split() -> None:
    """DP1 — and it is one of the five values migration 002's `CHECK` added."""
    clean = classify(evidence(mechanical=None, tail=tail(ending=TurnEnding.ENDED_TURN)))
    assert clean.decided_by is DecidedBy.HEURISTIC
    assert clean.stop_reason is StopReason.COMPLETED
    assert clean.confidence < CONFIDENT_ENOUGH

    incomplete = classify(
        evidence(mechanical=None, tasks_total=3, tasks_done=1, tail=tail(ending=TurnEnding.ENDED_TURN))
    )
    assert incomplete.decided_by is DecidedBy.HEURISTIC
    assert incomplete.stop_reason is StopReason.INCOMPLETE
    assert incomplete.missing != ()


def test_other_and_absent_endings_are_unknown_and_counted() -> None:
    """DP7 — a turn ending nobody mapped decides nothing, and saying nothing is
    not the same as saying "fine". The adapter already resolves both to a
    mechanical `unknown`; this is the guard for a record that reaches the
    classifier without one, which is what `replay` reads out of the log."""
    for ending in (TurnEnding.OTHER, TurnEnding.ABSENT):
        given = classify(evidence(mechanical=None, tail=tail(ending=ending)))
        assert given.stop_reason is StopReason.UNKNOWN, ending
        assert given.decided_by is DecidedBy.MECHANICAL
        assert given.bucket is Bucket.ERROR
        assert given.next_actions != ()


def test_the_split_only_runs_on_a_clean_turn_ending() -> None:
    """E-M2-12: a missing transcript is an `ABSENT` tail, and a record that
    cannot establish how the turn ended cannot be split."""
    for ending in TurnEnding:
        given = classify(
            evidence(mechanical=None, tasks_total=5, tasks_done=0, tail=tail(ending=ending))
        )
        if ending is TurnEnding.ENDED_TURN:
            assert given.stop_reason is StopReason.INCOMPLETE
        else:
            assert given.stop_reason is StopReason.UNKNOWN, ending


def test_every_verdict_has_actions_unless_confidently_completed() -> None:
    """C-M2-2 / §14 — the one exemption is the row that needs nothing."""
    for reason in StopReason:
        given = classify(evidence(mechanical=reason, mechanical_detail="x"))
        if given.stop_reason is StopReason.COMPLETED and given.confidence >= CONFIDENT_ENOUGH:
            assert given.next_actions == ()
        else:
            assert given.next_actions != (), reason
        assert len(given.next_actions) <= 3


def test_a_low_confidence_completed_still_carries_an_action() -> None:
    """DP10's price, at the seam where it is paid."""
    clean = classify(evidence(mechanical=None, tail=tail(ending=TurnEnding.ENDED_TURN)))
    assert clean.stop_reason is StopReason.COMPLETED
    assert clean.bucket is Bucket.FINISHED
    assert [action.text for action in clean.next_actions] == ["Review the diff"]


def test_waiting_on_is_none_at_m2() -> None:
    """G-M2-7 — `blocked_external`'s two buildable sources are M4's
    `report_blocked()` and M5's work-item status, so nothing here can name what
    a session waits on without guessing."""
    blocked = classify(
        evidence(
            mechanical=None,
            tail=tail(
                ending=TurnEnding.ENDED_TURN,
                last_assistant_text="Done my part — waiting on review before merging.",
            ),
        )
    )
    assert blocked.stop_reason is StopReason.BLOCKED_EXTERNAL
    assert blocked.waiting_on is None
    assert blocked.next_actions[0].text == "Chase — what it is waiting on is not recorded"


def test_why_is_never_longer_than_the_column() -> None:
    """E-M2-28 — every heuristic firing at once still fits §7's width, and the
    untruncated sentence is what the log record keeps."""
    everything = evidence(
        mechanical=None,
        tasks_total=9,
        tasks_done=0,
        brief="write and edit and create every file",
        tail=tail(
            ending=TurnEnding.ENDED_TURN,
            last_assistant_text="I'll do it.",
            promise_followed_by_tool_use=False,
            failures=tuple(
                ToolFailure(tool_use_id=f"t{i}", name="Bash", entry_index=i) for i in range(3)
            ),
        ),
    )
    given = classify(everything)
    assert len(given.why) <= WHY_MAX
    assert given.why.endswith("…")
    assert len(split_completeness(everything).why) > WHY_MAX


def test_every_verdict_is_a_verdict() -> None:
    for reason in StopReason:
        given = classify(evidence(mechanical=reason, mechanical_detail=None))
        assert isinstance(given, Verdict)
        assert given.why != ""
        assert given.bucket in BUCKET_ORDER


# ----- D34's one call site ----------------------------------------------------


def test_classify_end_turn_returns_the_heuristic_result() -> None:
    """D34 — byte-identical, today and until the lane is built."""
    record = evidence(mechanical=None, tasks_total=4, tasks_done=1)
    assert classify_end_turn(record) == split_completeness(record)


def test_classify_end_turn_has_one_call_site() -> None:
    """P-M2-11 — AST over the shipped tree. Building the deferred lane means
    filling that function in; **nothing else in the system moves**, and this is
    what keeps that true."""
    call_sites = [
        path
        for path in sources()
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "classify_end_turn")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "classify_end_turn")
        )
    ]
    assert len(call_sites) == 1
    assert call_sites[0].name == "verdict.py"


def test_no_llm_lane_exists() -> None:
    """P-M2-11 — no `Classifier`, no model id, no `anthropic`, no prompt
    constant, no credential check anywhere in `src/shepherd/`.

    An interface with zero implementations behind it is D9's mistake in its
    purest form, so the seam is not written *and* its absence is asserted:
    a seam nobody notices growing is how the first one arrived.
    """
    offenders: list[str] = []
    for path in sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Classifier" in node.name:
                offenders.append(f"{path.name}: class {node.name}")
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}: imports {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in {"anthropic", "openai", "httpx", "requests"}
                ]
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {
                "anthropic",
                "openai",
                "httpx",
                "requests",
            }:
                offenders.append(f"{path.name}: imports from {node.module}")
        for literal in literals(tree):
            if MODEL_ID.search(literal) and not names_a_real_capture(literal):
                offenders.append(f"{path.name}: {literal!r} looks like a model id")
            lowered = literal.lower()
            offenders += [
                f"{path.name}: {literal!r} looks like a credential"
                for word in CREDENTIAL_WORDS
                if word.lower() in lowered
            ]
    assert offenders == []


def test_the_llm_scan_would_notice_a_lane_being_built() -> None:
    """The negative half: the scan above is not vacuous."""
    assert MODEL_ID.search("claude-opus-4-20250514")


def test_an_invented_capture_path_is_still_caught() -> None:
    """T13-3's exemption is a filesystem fact, not a spelling.

    A path that looks exactly like a citation but names nothing on disk is still
    a model id. Without this, the fix would be a hole the shape of any string
    ending in a slash — which is the failure mode the rule exists to prevent.
    """
    invented = "gap-fill/keys-claude-99999999T999999Z/made-up.txt"
    assert MODEL_ID.search(invented), "the shape rule must still match it"
    assert not names_a_real_capture(invented), "it names nothing on disk"


def test_a_real_capture_path_is_evidence_not_a_model_id() -> None:
    """The positive half, against a capture that is really there."""
    real = "gap-fill/keys-claude-20260914T180105Z"
    assert MODEL_ID.search(real), "this is exactly the collision T13-3 hit"
    assert names_a_real_capture(real), f"{real} should exist under {PROBE_ROOT}"
    assert MODEL_ID.search("gpt-4o")
    assert not MODEL_ID.search("shepherd-controld")


def test_the_deferred_lane_is_documented_where_it_would_be_built() -> None:
    """The docstring is the handover: a reader who arrives to build the lane
    must find why there is no seam, not rediscover the argument."""
    doc = classify_end_turn.__doc__ or ""
    assert "D34" in doc
    assert "Classifier" in doc


# ----- the two provable properties --------------------------------------------


def mutations(count: int) -> list[StopEvidence]:
    """Null, absent, empty, oversized and **wrong-typed** records (P-M2-2).

    Wrong-typed is not paranoia: a record read back out of the stop log is JSON
    that some earlier build wrote, and `replay` must survive one bad line
    rather than dying on it.
    """
    rng = random.Random(20260917)
    reasons: list[object] = [None, *list(StopReason), "not_a_reason", 7]
    endings: list[object] = [*list(TurnEnding), None, "nonsense"]
    texts: list[object] = [None, "", "x" * 5000, "I'll do it", 3, ["not", "a", "string"]]
    numbers: list[object] = [0, 3, -1, None, "4", 10**9, 1.5]
    records: list[StopEvidence] = []
    for _ in range(count):
        broken_tail = TranscriptTail(
            ending=rng.choice(endings),  # type: ignore[arg-type]
            last_assistant_text=rng.choice(texts),  # type: ignore[arg-type]
            entry_count=rng.choice(numbers),  # type: ignore[arg-type]
            tool_uses=rng.choice(
                [(), (ToolUseRef("t", "Write", 0),), (ToolUseRef("t", None, 0),), None]  # type: ignore[arg-type,list-item]
            ),  # type: ignore[arg-type]
            failures=rng.choice(
                [(), tuple(ToolFailure(f"t{i}", "Bash", i) for i in range(3)), None]  # type: ignore[arg-type,list-item]
            ),  # type: ignore[arg-type]
            promise_followed_by_tool_use=rng.choice([True, False, None, "maybe"]),  # type: ignore[arg-type]
            skipped_lines=rng.choice(numbers),  # type: ignore[arg-type]
            truncated=rng.choice([True, False, None]),  # type: ignore[arg-type]
        )
        records.append(
            evidence(
                record_version=rng.choice([1, 0, 99, None]),
                session_id=rng.choice(["01S", "", None]),
                mechanical=rng.choice(reasons),
                mechanical_detail=rng.choice(texts),
                tail=broken_tail,
                tasks_total=rng.choice(numbers),
                tasks_done=rng.choice(numbers),
                brief=rng.choice(texts),
            )
        )
    return records


def test_classify_never_raises() -> None:
    """P-M2-2 — 500 mutations, every field null, empty, oversized, wrong-typed."""
    records = mutations(500)
    assert len(records) == 500
    for record in records:
        given = classify(record)
        assert isinstance(given, Verdict)
        assert given.bucket in BUCKET_ORDER
        assert len(given.why) <= WHY_MAX
        assert len(given.next_actions) <= 3


def test_an_unreadable_record_is_unknown_and_never_a_confident_answer() -> None:
    """The guard is a **boundary** guard, not a blanket `except`: a record that
    cannot be read is `unknown` at confidence 0, which the fleet counts. A
    record that reads fine takes the ordinary path, so a real bug in a rule is
    never laundered into a green row."""
    unreadable = evidence(tasks_total="lots", tasks_done=None, tail=tail(ending=TurnEnding.ENDED_TURN))  # type: ignore[arg-type]
    given = classify(unreadable)
    assert given.stop_reason is StopReason.UNKNOWN
    assert given.confidence == 0.0
    assert given.next_actions != ()


def test_classify_is_deterministic() -> None:
    """P-M2-1 — the same record answers the same way, always.

    The matrix is every turn ending crossed with every mechanical reason and
    both ledger states; the mutations add 500 records nobody designed. (The
    *corpus* lane — both fixture corpora replayed end to end — is T17's, and it
    reads the same function.)
    """
    matrix = [
        evidence(
            mechanical=reason,
            mechanical_detail="detail",
            tasks_total=total,
            tasks_done=done,
            tail=tail(ending=ending, last_assistant_text="I'll do it"),
        )
        for reason in (None, *list(StopReason))
        for ending in TurnEnding
        for total, done in ((0, 0), (3, 1))
    ]
    for record in [*matrix, *mutations(500)]:
        first, second = classify(record), classify(replace(record))
        assert first == second
