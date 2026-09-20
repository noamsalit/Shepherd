"""§8's completeness split, mechanically (T8, `signals/heuristics.py`).

Five pure predicates over one `StopEvidence`, no model and no credential. The
discipline under every test here is the one M1's refusal classifier established:
**the matching is literal**, an uncaptured wording matches nothing, and the
heuristic **under-fires rather than inventing** a verdict (principle 5 applied
to a classifier).
"""

from __future__ import annotations

import ast
import collections
import json
from dataclasses import replace
from pathlib import Path

from shepherd.core.stops import (
    CONFIDENT_ENOUGH,
    HEURISTIC_COMPLETED_CONFIDENCE,
    WHY_MAX,
    STOP_RECORD_VERSION,
    StopEvidence,
    StopReason,
    ToolFailure,
    ToolUseRef,
    TranscriptTail,
    TurnEnding,
)
from shepherd.signals.heuristics import (
    CHANGE_PHRASES,
    FAILURE_TAIL_N,
    HEURISTICS,
    PROMISE_PHRASES,
    WAITING_PHRASES,
    is_promise,
    split_completeness,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"
CORPUS = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "hooks" / "live"
HEURISTICS_MODULE = REPO_ROOT / "src" / "shepherd" / "signals" / "heuristics.py"


def tail(**overrides: object) -> TranscriptTail:
    base = dict(
        ending=TurnEnding.ENDED_TURN,
        last_assistant_text=None,
        entry_count=4,
        tool_uses=(),
        failures=(),
        promise_followed_by_tool_use=None,
        skipped_lines=0,
        truncated=False,
    )
    base.update(overrides)
    return TranscriptTail(**base)  # type: ignore[arg-type]


def evidence(**overrides: object) -> StopEvidence:
    base = dict(
        record_version=STOP_RECORD_VERSION,
        session_id="01SESSION",
        engine_session_id="e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
        received_at="2026-09-17T01:04:18.671Z",
        mechanical=None,
        mechanical_detail=None,
        tail=tail(),
        tasks_total=0,
        tasks_done=0,
        brief=None,
        auto_compact_pending=False,
        quota_notice=False,
        process_exit_observed=False,
        exit_code=None,
    )
    base.update(overrides)
    return StopEvidence(**base)  # type: ignore[arg-type]


def headings() -> set[str]:
    return {
        line.lstrip("#").strip()
        for line in SCHEMAS.read_text().splitlines()
        if line.startswith("#")
    }


# ----- the citation rule ------------------------------------------------------


def test_every_heuristic_cites_an_existing_section() -> None:
    """P-M2-13 / K1 — the only mechanical enforcement of the first hard rule.

    A rule whose `evidence` names a section that is not in `data-schemas.md` is
    a rule asserting a shape nobody captured.
    """
    known = headings()
    assert len(HEURISTICS) == 5
    for rule in HEURISTICS:
        assert rule.evidence.startswith("§"), rule.name
        section = rule.evidence.removeprefix("§").split(" — ")[0]
        assert section in known, (rule.name, section)


def test_the_citation_check_would_notice_an_invented_section() -> None:
    """The negative half: the assertion above is not vacuous."""
    assert "Transcript entry: `assistant`" in headings()
    assert "Transcript entry: `there is no such section`" not in headings()


# ----- heuristic 1: the open task ledger --------------------------------------


def test_open_task_ledger_fires_on_the_one_corpus_session_with_an_open_task() -> None:
    """The whole fixture, measured — and it is thin, which is the point.

    Across the **50** captured sessions there are exactly **3** `TaskCreated`
    and **2** `TaskCompleted` events, and they fall in two sessions:
    `8bbcceab…` (1 created, 1 completed — closed) and `0ef819b5…` (2 created,
    1 completed — **one open task**). That single session is the entire
    positive evidence for §8's "strongest and cheapest" heuristic, so the test
    says so rather than letting a reader assume a corpus behind it.
    """
    created: collections.Counter[str] = collections.Counter()
    completed: collections.Counter[str] = collections.Counter()
    sessions: set[str] = set()
    for path in sorted(CORPUS.glob("*/events.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            payload = json.loads(line).get("payload") or {}
            session_id = payload.get("session_id")
            if session_id:
                sessions.add(session_id)
            name = payload.get("hook_event_name")
            if name == "TaskCreated":
                created[session_id] += 1
            elif name == "TaskCompleted":
                completed[session_id] += 1

    assert len(sessions) == 50
    assert sum(created.values()) == 3
    assert sum(completed.values()) == 2
    open_ledgers = {s: created[s] - completed[s] for s in created if created[s] > completed[s]}
    assert list(open_ledgers.values()) == [1]

    only = next(iter(open_ledgers))
    fired = split_completeness(
        evidence(tasks_total=created[only], tasks_done=completed[only])
    )
    assert fired.reason is StopReason.INCOMPLETE
    assert "open" in fired.why
    assert fired.missing != ()

    closed = split_completeness(evidence(tasks_total=1, tasks_done=1))
    assert closed.reason is StopReason.COMPLETED


# ----- heuristic 2: the unkept promise ----------------------------------------


def test_unkept_promise_needs_both_the_phrase_and_the_absence() -> None:
    promised = "I'll run both commands as requested — one Bash call each."
    assert is_promise(promised)
    both = split_completeness(
        evidence(tail=tail(last_assistant_text=promised, promise_followed_by_tool_use=False))
    )
    assert both.reason is StopReason.INCOMPLETE

    phrase_only = split_completeness(
        evidence(tail=tail(last_assistant_text=promised, promise_followed_by_tool_use=None))
    )
    assert phrase_only.reason is StopReason.COMPLETED

    absence_only = split_completeness(
        evidence(tail=tail(last_assistant_text="DONE", promise_followed_by_tool_use=False))
    )
    assert absence_only.reason is StopReason.COMPLETED


def test_kept_promise_does_not_fire() -> None:
    kept = split_completeness(
        evidence(
            tail=tail(
                last_assistant_text="I'll launch a background agent to probe for you.",
                promise_followed_by_tool_use=True,
            )
        )
    )
    assert kept.reason is StopReason.COMPLETED


def test_no_promise_is_not_a_broken_promise() -> None:
    """`None` is "there was no promise to judge" — never "the promise failed"."""
    assert split_completeness(
        evidence(tail=tail(last_assistant_text="OK", promise_followed_by_tool_use=None))
    ).reason is StopReason.COMPLETED


def test_the_promise_vocabulary_is_captured_wordings() -> None:
    """Each phrase is a real last-assistant text from the probe corpus, and
    the predicate is the one `read_tail` is meant to be injected with."""
    for captured in (
        "I'll execute these steps in order, one tool call per step.",
        "I'll run these bash commands sequentially as requested.",
        "I'll follow these steps one at a time. First, let me load the tool schema.",
        "I've started the sleep command in the background. I'll wait for it.",
    ):
        assert is_promise(captured), captured
    assert PROMISE_PHRASES != ()


def test_unmatched_wording_under_fires_rather_than_inventing() -> None:
    """An uncaptured phrasing matches nothing, and nothing is guessed."""
    invented = "Verily, mine next deed shall be the running of yon command."
    assert not is_promise(invented)
    result = split_completeness(
        evidence(tail=tail(last_assistant_text=invented, promise_followed_by_tool_use=False))
    )
    assert result.reason is StopReason.COMPLETED
    assert result.fired == ()


def test_a_curly_apostrophe_is_the_same_promise() -> None:
    """A normalisation, not a second vocabulary: the two spellings of one
    apostrophe are the same word, and doubling every row would be a list that
    rots at the first addition."""
    assert is_promise("I’ll run the command now.")


# ----- heuristic 3: the failure tail ------------------------------------------


def failures(*names: str | None) -> tuple[ToolFailure, ...]:
    return tuple(
        ToolFailure(tool_use_id=f"toolu_{i}", name=name, entry_index=i)
        for i, name in enumerate(names)
    )


def test_failure_tail_needs_three_on_the_same_tool() -> None:
    assert FAILURE_TAIL_N == 3
    three_same = split_completeness(
        evidence(tail=tail(failures=failures("Bash", "Bash", "Bash")))
    )
    assert three_same.reason is StopReason.INCOMPLETE

    two_same = split_completeness(evidence(tail=tail(failures=failures("Bash", "Bash"))))
    assert two_same.reason is StopReason.COMPLETED

    three_mixed = split_completeness(
        evidence(tail=tail(failures=failures("Bash", "Write", "Bash")))
    )
    assert three_mixed.reason is StopReason.COMPLETED


def test_an_unattributable_failure_never_counts_toward_the_tail() -> None:
    """E-M2-17 — an unpairable `is_error` result keeps `name=None`; three
    unknowns are not three failures on one tool."""
    unknown = split_completeness(evidence(tail=tail(failures=failures(None, None, None))))
    assert unknown.reason is StopReason.COMPLETED


def test_the_failure_tail_is_the_last_three_not_any_three() -> None:
    recovered = split_completeness(
        evidence(tail=tail(failures=failures("Bash", "Bash", "Bash", "Write")))
    )
    assert recovered.reason is StopReason.COMPLETED


# ----- heuristic 4: the no-op session -----------------------------------------


def tool_uses(*names: str) -> tuple[ToolUseRef, ...]:
    return tuple(
        ToolUseRef(tool_use_id=f"toolu_{i}", name=name, entry_index=i)
        for i, name in enumerate(names)
    )


def test_no_op_session_fires_when_the_brief_asked_for_a_change() -> None:
    asked = "write a note to /tmp/probe.txt"
    no_op = split_completeness(evidence(brief=asked, tail=tail(tool_uses=tool_uses("Bash"))))
    assert no_op.reason is StopReason.INCOMPLETE

    did_it = split_completeness(
        evidence(brief=asked, tail=tail(tool_uses=tool_uses("Bash", "Write")))
    )
    assert did_it.reason is StopReason.COMPLETED

    read_only_brief = split_completeness(
        evidence(brief="echo hello twice", tail=tail(tool_uses=tool_uses("Bash")))
    )
    assert read_only_brief.reason is StopReason.COMPLETED
    assert CHANGE_PHRASES != ()


def test_no_op_session_uses_the_tail_not_repos_touched() -> None:
    """`repos_touched` has a known cross-repo hole (inherited blocker T11-3);
    the tail does not. The AST says so, because a comment cannot."""
    source = HEURISTICS_MODULE.read_text()
    tree = ast.parse(source)
    names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "repos_touched" not in names
    assert "repos_touched" not in {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


# ----- heuristic 5: the blocked phrasing --------------------------------------


BLOCKED_TEXT = "Finished my part — waiting on review before merging."


def test_blocked_phrasing_requires_zero_open_tasks() -> None:
    """§8 makes the rule conditional on an empty ledger, which is what keeps it
    disjoint from heuristic 1."""
    clear = split_completeness(
        evidence(tail=tail(last_assistant_text=BLOCKED_TEXT), tasks_total=2, tasks_done=2)
    )
    assert clear.reason is StopReason.BLOCKED_EXTERNAL

    open_ledger = split_completeness(
        evidence(tail=tail(last_assistant_text=BLOCKED_TEXT), tasks_total=2, tasks_done=1)
    )
    assert open_ledger.reason is StopReason.INCOMPLETE
    assert WAITING_PHRASES != ()


def test_blocked_phrasing_outranks_incomplete() -> None:
    """D18's argument: "waiting on a review" is a better answer than
    "incomplete", and a worker that retries it wastes a slot."""
    both = evidence(
        tail=tail(
            last_assistant_text=BLOCKED_TEXT + " I'll pick it up after.",
            promise_followed_by_tool_use=False,
            failures=failures("Bash", "Bash", "Bash"),
        ),
    )
    result = split_completeness(both)
    assert result.reason is StopReason.BLOCKED_EXTERNAL
    assert len(result.fired) > 1
    assert result.fired[0] == "blocked_phrasing"


def test_a_permission_wait_is_not_blocked_external() -> None:
    """The nearest captured waiting wording is
    `"Permission required for step 5. Waiting for authorization…"`, and that is
    a `needs_you` row, not a session waiting on the outside world. It is left
    out of the vocabulary deliberately — over-firing here parks a work item
    that a single click would have unblocked."""
    waiting_on_a_human = split_completeness(
        evidence(
            tail=tail(
                last_assistant_text=(
                    "Permission required for step 5. Waiting for authorization to"
                    " write to `.claude/settings.local.json`."
                )
            )
        )
    )
    assert waiting_on_a_human.reason is not StopReason.BLOCKED_EXTERNAL


# ----- the resolver -----------------------------------------------------------


def test_no_heuristic_fires_means_completed_at_low_confidence() -> None:
    """ADR-M2-5 / DP10 — and the reason the corpus is not ~98% `unknown`.

    The price is paid elsewhere and it is not optional: this cohort is counted
    as `completed_low_confidence` (T2's `StopCounts`) and rendered beside the
    `unknown` rate, because a green chip nothing counts is principle 5 unmet
    for the largest cohort.
    """
    result = split_completeness(evidence())
    assert result.reason is StopReason.COMPLETED
    assert result.confidence == HEURISTIC_COMPLETED_CONFIDENCE
    assert result.confidence < CONFIDENT_ENOUGH
    assert result.fired == ()
    assert result.missing == ()
    assert result.why != ""


def test_a_fired_heuristic_is_never_more_confident_than_a_mechanical_reason() -> None:
    """§8 reserves 1.0 for the mechanical table."""
    fired = split_completeness(evidence(tasks_total=3, tasks_done=0))
    assert HEURISTIC_COMPLETED_CONFIDENCE < fired.confidence < 1.0


def test_the_split_keeps_the_untruncated_why() -> None:
    """E-M2-28's other half. The 120-char cap is `Verdict`'s invariant (T1) and
    is applied once, at the column; the split hands the **whole** sentence up
    so the log record keeps what the column had to drop."""
    everything = split_completeness(
        evidence(
            tasks_total=9,
            tasks_done=0,
            brief="write and edit and create every file",
            tail=tail(
                last_assistant_text="I'll do it. " + BLOCKED_TEXT,
                promise_followed_by_tool_use=False,
                failures=failures("Bash", "Bash", "Bash"),
            ),
        )
    )
    assert len(everything.why) > WHY_MAX
    assert everything.why.endswith("the brief asked for a change and nothing was written")
    assert len(everything.fired) == 4


def test_every_finding_reaches_the_missing_list() -> None:
    """D21's requeue items are built from `missing[]`, so a finding that never
    lands there is a finding no human is ever shown."""
    result = split_completeness(
        evidence(tasks_total=3, tasks_done=0, tail=tail(failures=failures("Bash", "Bash", "Bash")))
    )
    assert len(result.fired) == 2
    assert len(result.missing) == 2
    assert all(item for item in result.missing)


def test_derailed_is_never_produced() -> None:
    """P-M2-12 / G-M2-6 — no mechanical detector for "believed it finished but
    did something else" exists. That absence is the clearest measure of what
    D34 deferred, so it is asserted rather than left to be noticed."""
    assert StopReason.DERAILED not in {rule.reason for rule in HEURISTICS}
    for text in (None, "DONE", BLOCKED_TEXT, "I'll run it"):
        for total, done in ((0, 0), (3, 1)):
            result = split_completeness(
                evidence(tasks_total=total, tasks_done=done, tail=tail(last_assistant_text=text))
            )
            assert result.reason is not StopReason.DERAILED


def test_the_split_is_deterministic_and_never_raises() -> None:
    weird = evidence(
        brief="",
        tasks_total=-5,
        tasks_done=7,
        tail=tail(last_assistant_text="", failures=failures(None), tool_uses=tool_uses("")),
    )
    assert split_completeness(weird) == split_completeness(replace(weird))


def test_heuristics_are_pure() -> None:
    """AST: no clock, no file, no store. A rule that reads the world is not a
    rule the golden lane can replay."""
    tree = ast.parse(HEURISTICS_MODULE.read_text())
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not {name for name in imported if name.startswith("shepherd.store")}
    assert "datetime" not in imported
    assert "time" not in imported
    assert "shepherd.core.clock" not in imported
