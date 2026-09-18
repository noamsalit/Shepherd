"""§8's completeness split — the five heuristics, mechanically (T8).

Five pure predicates over one `StopEvidence`, each carrying the section of
`docs/specs/data-schemas.md` its evidence comes from. No model, no credential,
no prompt: D34 defers that lane, and this module is what runs instead of it.

**The matching is literal.** Every vocabulary below is a list of *captured
wordings*, and a phrasing nobody captured matches nothing — the heuristic
**under-fires rather than inventing** a verdict. That is principle 5 applied to
a classifier, and it is the same discipline M1's refusal classifier is held to:
a rule that guesses is a rule whose wrong answers are invisible.

**What the five read, and why (DP3).** D24 discards the events after folding,
so heuristic 1 reads the *folded columns* (`tasks_total`, `tasks_done`) rather
than a history nothing keeps, and heuristics 2–5 read the **neutral transcript
tail** the adapter projected once, at the stop. Nothing here opens a file.

**Resolution order, stated because two can fire at once.** 5 before 1–4: §8
makes blocked phrasing conditional on an empty ledger, so it is already
disjoint from 1 but not from 2–4, and *"waiting on a review"* is a better
answer than *"incomplete"* — a worker that retries a blocked session wastes a
slot, which is D18's whole argument. Then 1 (§8: "strongest and cheapest"),
then 3, 2, 4. Every rule that fires contributes its finding to `missing[]`, and
the **first** one decides the reason.

**`derailed` is not here and cannot be.** No mechanical detector for "believed
it finished but did something else" exists (G-M2-6). That absence is the
single clearest measure of what D34 deferred, so a test asserts it.

**`blocked_external`'s two buildable sources are not here either.** D18 ranks
them: self-declaration (M4's `report_blocked`) and the linked work item's
`status_class` (M5). Neither exists at M2, which is why `waiting_on` is `None`
on every verdict this module can produce (G-M2-7) and why heuristic 5 yields a
*candidate* rather than a naming.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shepherd.core.stops import (
    CONFIDENT_ENOUGH,
    HEURISTIC_COMPLETED_CONFIDENCE,
    StopEvidence,
    StopReason,
)

__all__ = [
    "CHANGE_PHRASES",
    "FAILURE_TAIL_N",
    "HEURISTICS",
    "HEURISTIC_FIRED_CONFIDENCE",
    "PROMISE_PHRASES",
    "WAITING_PHRASES",
    "Heuristic",
    "SplitResult",
    "is_promise",
    "split_completeness",
]

#: §8's "last 3 signals … on the same tool".
FAILURE_TAIL_N = 3

#: A heuristic that fired matched a literal wording or counted a column, so it
#: is worth acting on — and no more certain than that. **1.0 is reserved for
#: the mechanical table** (§8), and this is deliberately the same constant that
#: decides whether a row needs a human at all, rather than a sixth number
#: nobody can trace.
HEURISTIC_FIRED_CONFIDENCE = CONFIDENT_ENOUGH

#: Heuristic 2's vocabulary. Every row is a **captured** last-assistant wording
#: from the probe corpus (`…/2026-09-14-schemas/**/*stdout.jsonl` and the
#: transcript copies): "I'll execute these steps in order", "I'll run both
#: commands as requested", "I'll launch a background agent", "First, let me
#: load the tool schema". §8's own examples ("I'll now run…", "next I'll…",
#: "let me…") are the same three stems.
PROMISE_PHRASES: tuple[str, ...] = (
    "i'll ",
    "i will ",
    "let me ",
    "i'm going to ",
    "next, i'll",
    "now i'll",
)

#: Heuristic 5's vocabulary: §8's four categories — review, merge, CI, deploy —
#: in the waiting constructions English actually uses.
#:
#: **Evidence gap, recorded rather than papered over.** No probe session ever
#: waited on a review, so unlike the other two vocabularies these rows are
#: **spec-derived, not corpus-derived** (see the blocker file, T8-1). The
#: nearest captured waiting wording is *"Permission required for step 5.
#: Waiting for authorization to write…"* — and that is a `needs_you` row, not a
#: session waiting on the outside world, so it is deliberately **not** here.
#: Over-firing parks a work item that one click would have unblocked.
WAITING_PHRASES: tuple[str, ...] = (
    "waiting on review",
    "waiting for review",
    "waiting on a review",
    "waiting for a review",
    "waiting on the review",
    "waiting on merge",
    "waiting for merge",
    "waiting on the merge",
    "waiting for ci",
    "waiting on ci",
    "waiting for the ci",
    "waiting on deploy",
    "waiting for deploy",
    "waiting on the deploy",
    "blocked on review",
    "blocked on merge",
    "blocked on ci",
    "blocked on deploy",
)

#: Heuristic 4's brief vocabulary: the verbs a brief uses when it asks for a
#: **change** to the tree, as opposed to a question. Captured briefs in the
#: corpus use `write`, `create`, `install`, `remove` and `delete`; the rest are
#: §8's own word ("a session whose brief asked for changes").
CHANGE_PHRASES: tuple[str, ...] = (
    "write",
    "edit",
    "create",
    "add ",
    "fix",
    "implement",
    "update",
    "refactor",
    "rename",
    "delete",
    "remove",
    "change",
    "patch",
    "install",
)

#: The tool names heuristic 4 counts as "it changed something". API vocabulary
#: (the tool's own name), not hook vocabulary — the tail carries these verbatim
#: from the `tool_use` blocks.
CHANGE_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})

#: The two spellings of one apostrophe, folded before matching. A
#: *normalisation*, not a second vocabulary: doubling every row would be a list
#: that rots at the first addition.
_CURLY_APOSTROPHE = "’"


def _normalised(text: str) -> str:
    return text.replace(_CURLY_APOSTROPHE, "'").lower()


def _matches(text: str | None, phrases: tuple[str, ...]) -> bool:
    """Literal containment, case- and apostrophe-folded. Nothing else."""
    if not text:
        return False
    folded = _normalised(text)
    return any(phrase in folded for phrase in phrases)


def is_promise(text: str) -> bool:
    """Does this assistant text promise a next action? (heuristic 2)

    Exported because the promise **vocabulary** belongs here, in `signals/`,
    while the *ordering* fact — was a tool call issued after the promise? —
    can only be seen in the transcript. `read_tail` takes this predicate as a
    parameter for exactly that reason: what counts as a promise would be a rule
    hiding in an adapter.
    """
    return _matches(text, PROMISE_PHRASES)


def _open_task_ledger(evidence: StopEvidence) -> bool:
    return evidence.tasks_total - evidence.tasks_done > 0


def _unkept_promise(evidence: StopEvidence) -> bool:
    """Both halves, always: the phrase **and** the absence.

    `promise_followed_by_tool_use` is `None` when there was no promise to
    judge, and `None` is not `False` — "nobody asked" is not "the promise was
    broken".
    """
    return (
        evidence.tail.promise_followed_by_tool_use is False
        and is_promise(evidence.tail.last_assistant_text or "")
    )


def _failure_tail(evidence: StopEvidence) -> bool:
    """The last `FAILURE_TAIL_N` failures, all attributed to the same tool.

    An unpairable `is_error` result keeps `name=None` (E-M2-17) and is counted
    rather than attributed, so three unknowns are never three failures on one
    tool.
    """
    recent = evidence.tail.failures[-FAILURE_TAIL_N:]
    if len(recent) < FAILURE_TAIL_N:
        return False
    names = {failure.name for failure in recent}
    return len(names) == 1 and None not in names


def _no_op_session(evidence: StopEvidence) -> bool:
    changed = any(use.name in CHANGE_TOOLS for use in evidence.tail.tool_uses)
    return not changed and _matches(evidence.brief, CHANGE_PHRASES)


def _blocked_phrasing(evidence: StopEvidence) -> bool:
    return (
        evidence.tasks_total - evidence.tasks_done == 0
        and _matches(evidence.tail.last_assistant_text, WAITING_PHRASES)
    )


@dataclass(frozen=True)
class Heuristic:
    """One rule. `evidence` names the `data-schemas.md` section its input was
    captured in — non-empty, and checked against the real headings (P-M2-13).
    """

    name: str
    fires: Callable[[StopEvidence], bool]
    reason: StopReason
    why: str
    evidence: str


#: The five, **in resolution order**.
#:
#: Heuristic 1's citation is the section that enumerates the two ledger events,
#: rather than their own section heading: `signals/` may not spell an engine
#: event name anywhere but the one declared `FoldRule(evidence=…)` position
#: (K13), and the ledger's own heading *is* two event names. The fold rules
#: that write these two columns carry the verbatim citation at their own
#: definition site. See the blocker file, T8-2.
HEURISTICS: tuple[Heuristic, ...] = (
    Heuristic(
        name="blocked_phrasing",
        fires=_blocked_phrasing,
        reason=StopReason.BLOCKED_EXTERNAL,
        why="last message waits on something outside, ledger empty",
        evidence="§Transcript entry: `assistant`",
    ),
    Heuristic(
        name="open_task_ledger",
        fires=_open_task_ledger,
        reason=StopReason.INCOMPLETE,
        why="tasks still open at the stop",
        evidence="§Hook event names (the enum) — the task-ledger pair, folded",
    ),
    Heuristic(
        name="failure_tail",
        fires=_failure_tail,
        reason=StopReason.INCOMPLETE,
        why="the last three tool calls failed on one tool",
        evidence="§Transcript entry: `user`",
    ),
    Heuristic(
        name="unkept_promise",
        fires=_unkept_promise,
        reason=StopReason.INCOMPLETE,
        why="promised a next step that never ran",
        evidence="§Transcript entry: `assistant`",
    ),
    Heuristic(
        name="no_op_session",
        fires=_no_op_session,
        reason=StopReason.INCOMPLETE,
        why="the brief asked for a change and nothing was written",
        evidence="§Transcript entry: `assistant`",
    ),
)

#: What a clean stop says. It is a *sentence*, not an empty string: §7's `why`
#: column is rendered to a human, and "" reads as a bug.
CLEAN_WHY = "no open tasks, no unkept promise, no failure tail, no waiting language"


@dataclass(frozen=True)
class SplitResult:
    """The completeness half of a verdict. `fired` is the audit trail — which
    rules matched, in order — and it is what a tuning pass reads."""

    reason: StopReason
    why: str
    confidence: float
    missing: tuple[str, ...]
    fired: tuple[str, ...]


def split_completeness(evidence: StopEvidence) -> SplitResult:
    """One record in, one completeness answer out. Pure; never raises.

    **A null result is `completed`, not `unknown`** (DP10 / ADR-M2-5) — at
    `HEURISTIC_COMPLETED_CONFIDENCE`, which is below `CONFIDENT_ENOUGH`, so
    D21's table gives the row `Review the diff` rather than an empty action
    list and a green chip. This is the one place M2 does not follow a numbered
    decision's literal words: D34 says the residue is `unknown`, and the
    corpus measures 3 task events across 50 sessions, so the literal reading
    paints ~98% of the fleet red and drowns the very metric D34 wants. **What
    it owes D34 is paid elsewhere and is not optional:** this cohort is counted
    as `completed_low_confidence` and rendered beside the `unknown` rate, so
    the tuning signal survives in the product rather than only in the argument.

    Reversing it, should a reviewer prefer the literal reading, is one line:
    return `StopReason.UNKNOWN` here when `fired == ()`.
    """
    fired = tuple(rule for rule in HEURISTICS if rule.fires(evidence))
    if not fired:
        return SplitResult(
            reason=StopReason.COMPLETED,
            why=CLEAN_WHY,
            confidence=HEURISTIC_COMPLETED_CONFIDENCE,
            missing=(),
            fired=(),
        )
    return SplitResult(
        reason=fired[0].reason,
        why="; ".join(rule.why for rule in fired),
        confidence=HEURISTIC_FIRED_CONFIDENCE,
        missing=tuple(rule.why for rule in fired),
        fired=tuple(rule.name for rule in fired),
    )
