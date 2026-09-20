"""T17 — the stop fixtures: a real stop record, paired with a real tail.

**Every byte here is captured.** A fixture is one stop occurrence replayed out
of a probe corpus — the same `Signal` the adapter projects at runtime, over the
same folded counters the fold produces — assembled by the **production**
`build_stop_evidence` and classified by the production `classify`. Nothing is
mocked and no payload is written.

**What composition is, and what it costs (r3 BLOCKING 3).** A stop record whose
transcript cannot be read resolves to `TurnEnding.ABSENT` → `unknown`, and the
suite may not read the engine's own project directory (**P-M2-15**: 424 of the
429 corpus payloads name a `transcript_path` that still exists on this host, and
reading one would make this lane depend on a directory the user may clear).
Only **1 of 50** corpus-1 sessions has a checked-in transcript copy, so a lane
built naively from corpus stops alone would call a majority of them `unknown` —
an artefact of the fixture set, not a measurement of the classifier. The fix is
composition, not a looser ceiling: pair each real stop record with a real tail
from the 19 checked-in copies. **Both halves are captured data; only the
pairing is ours**, every composed fixture names both captures in `sources`, and
`test_composed_fixtures_name_their_captures` opens each one. **What this lane
therefore does not prove** is that the *specific* transcript belonging to a
*specific* corpus session said `end_turn` — that is T19's live lane, against a
session it creates itself.

**The expectations are declared, not recomputed.** `StopFixture.expected` comes
from §8's table and the plan's per-reason coverage table, written out here as
data. A fixture that read `mechanical_reason` to decide what it expected would
agree with the classifier by construction and could never disagree with it.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from golden.corpus import (
    REPO_ROOT,
    StopOccurrence,
    load_corpus,
    load_gapfill_corpus,
    stop_occurrences,
    transcript_copies,
)
from shepherd.core.stops import StopEvidence, StopReason, Verdict
from shepherd.engines.claude_code.evidence import build_stop_evidence
from shepherd.signals.heuristics import CHANGE_PHRASES, is_promise
from shepherd.signals.verdict import classify

EXPECTED_VERDICTS = Path(__file__).resolve().parent / "expected" / "verdicts.json"

#: P-M2-14's ceiling, measured over the fixture population below.
MAX_UNKNOWN_RATE = 0.20

#: The name prefix that marks a pairing as ours. A fixture whose stop record
#: and tail came from the same captured session is `real:`; anything else is
#: `composed:` and owes at least two `sources`.
COMPOSED_PREFIX = "composed:"
REAL_PREFIX = "real:"

#: The measured size of the population: 99 stop occurrences in corpus 1
#: (26 `Stop`, 23 `StopFailure`, 50 `SessionEnd`), 70 in corpus 2, and the 5
#: curated compositions below. An exact number, because a fixture set that
#: silently shrank is the same defect as a glob that silently matched nothing.
EXPECTED_CORPUS_ONE_STOPS = 99
EXPECTED_CORPUS_TWO_STOPS = 70
EXPECTED_CURATED = 5
EXPECTED_FIXTURE_COUNT = (
    EXPECTED_CORPUS_ONE_STOPS + EXPECTED_CORPUS_TWO_STOPS + EXPECTED_CURATED
)


# ----- §8's table, declared ---------------------------------------------------

#: §8's mechanical map from the engine's 13 `StopFailure.error` values, written
#: from the **spec**. Eight have a capture in corpus 1; the other five are
#: G-M2-5 and appear here only so a capture that ever arrives is checked
#: against a declaration rather than against the rule it is testing.
DECLARED_BY_ERROR: Mapping[str, StopReason] = {
    "rate_limit": StopReason.RATE_LIMITED,
    "overloaded": StopReason.RATE_LIMITED,
    "authentication_failed": StopReason.AUTH_FAILED,
    "oauth_org_not_allowed": StopReason.AUTH_FAILED,
    "verification_required": StopReason.AUTH_FAILED,
    "cloud_credential_error": StopReason.AUTH_FAILED,
    "account_on_hold": StopReason.ACCOUNT_BLOCKED,
    "billing_error": StopReason.ACCOUNT_BLOCKED,
    "invalid_request": StopReason.BAD_REQUEST,
    "model_not_found": StopReason.BAD_REQUEST,
    "server_error": StopReason.SERVER_ERROR,
    "max_output_tokens": StopReason.TRUNCATED,
    "unknown": StopReason.UNKNOWN,
}

#: §8's map from the 4 decided `SessionEnd.reason` values. The fifth, `other`,
#: is DP8's defer: it says the process ended and nothing about why.
DECLARED_BY_END_REASON: Mapping[str, StopReason] = {
    "prompt_input_exit": StopReason.USER_EXITED,
    "clear": StopReason.CLEARED,
    "logout": StopReason.LOGGED_OUT,
    "resume": StopReason.RESUMED_ELSEWHERE,
}
DEFERRING_END_REASON = "other"


# ----- the tails, each named and each real ------------------------------------


def _copy(stem: str) -> Path:
    """One checked-in transcript by session id. Never a path under `~/.claude`."""
    for path in transcript_copies():
        if path.stem == stem:
            return path
    raise AssertionError(f"no checked-in transcript copy named {stem}")


#: The clean tail every deferring stop is paired with: a real turn that ended
#: (`end_turn`), with a real `Write` among its tool calls — so heuristic 4
#: ("the brief asked for a change and nothing was written") cannot fire on a
#: pairing decision rather than on the capture.
TAIL_COMPLETED_STEM = "0141fab3-8bf8-4b69-be1f-89552ccfce5d"

#: A real turn whose last message promises a next step (*"I'll wait …"*) and
#: whose transcript contains no tool call after it — heuristic 2, captured
#: whole rather than composed.
TAIL_UNKEPT_PROMISE_STEM = "ea5a5348-c427-4438-b6f1-23a46e260b59"

#: A real turn carrying a real `is_error` tool result on `Bash`. The composed
#: version repeats that captured line until the failure tail is three long.
TAIL_FAILURE_STEM = "76d51cc7-3b32-4274-9ee4-e08f21f79042"

#: A real turn that called no change tool at all — heuristic 4's other half.
TAIL_NO_CHANGE_STEM = "667257d2-9430-4714-a8b1-fb07a95ae0bf"

#: C13's evidence: the pidfd run's own results file, cited by the one fixture
#: that says a process exit was observed.
PIDFD_RESULTS = "docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/results.json"


@dataclass(frozen=True)
class StopFixture:
    """One stop, one declared expectation, and the captures it is made of."""

    name: str
    evidence: StopEvidence
    expected: StopReason
    sources: tuple[str, ...]


def composed(fixture: StopFixture) -> bool:
    return fixture.name.startswith(COMPOSED_PREFIX)


# ----- what §8 says each occurrence should resolve to -------------------------


def _declared(occurrence: StopOccurrence, tail_reason: StopReason) -> StopReason:
    """§8's precedence, declared over the **capture's own** fields.

    Read this beside `mechanical_reason`, never from it: this is the spec's
    sentence and that is the implementation, and the lane exists to let them
    disagree.
    """
    error = occurrence.failure_error
    if error is not None:
        return DECLARED_BY_ERROR[error]
    end_reason = occurrence.end_reason
    if end_reason is not None and end_reason in DECLARED_BY_END_REASON:
        return DECLARED_BY_END_REASON[end_reason]
    if end_reason is not None and occurrence.prior.auto_compact_at:
        # §8's compaction bound: auto-compaction started and the session died
        # before it finished. Both guards, deliberately (r3 BLOCKING 1).
        return StopReason.CONTEXT_EXHAUSTED
    if occurrence.open_ledger:
        # Heuristic 1, §8's "strongest and cheapest": tasks still open.
        return StopReason.INCOMPLETE
    return tail_reason


# ----- assembling one fixture -------------------------------------------------


def _evidence(
    occurrence: StopOccurrence,
    *,
    transcript: Path | None,
    projects_root: Path,
    process_exit_observed: bool = False,
) -> StopEvidence:
    """The production assembly, with the transcript pointed at a capture.

    `transcript_path` is replaced on **every** signal, including the ones that
    do not need a tail: the captured value names a real path under the engine's
    own directory that still exists on this host, and `build_stop_evidence`
    would open it (P-M2-15). `None` means no tail is available, which is the
    honest state of a session whose transcript was never checked in.
    """
    signal = replace(occurrence.signal, transcript_path="" if transcript is None else str(transcript))
    record, _ = build_stop_evidence(
        signal=signal,
        prior=occurrence.prior,
        projects_root=projects_root,
        received_at=occurrence.signal.received_at,
        end_reason=occurrence.end_reason,
        auto_compact_pending=bool(occurrence.prior.auto_compact_at),
        quota_notice=bool(occurrence.prior.quota_notice_at),
        promise=is_promise,
        process_exit_observed=process_exit_observed,
        exit_code=None,
    )
    return record


def _population(
    occurrences: Sequence[StopOccurrence], *, projects_root: Path, completed_tail: Path
) -> list[StopFixture]:
    """Every captured stop, in corpus order, each with the tail it can have.

    Three pairings, and the name says which one a row got: a **mechanical**
    stop needs no tail and is given none (`real:`); a stop whose **own**
    transcript is checked in keeps it (`real:` — exactly one session in corpus
    1); everything else is `composed:` with the clean `end_turn` tail, which is
    why each of those rows names two captures.
    """
    fixtures: list[StopFixture] = []
    for occurrence in occurrences:
        own = _own_copy(occurrence.prior.engine_session_id)
        transcript: Path | None
        sources: tuple[str, ...]
        if _mechanical(occurrence):
            transcript, prefix, sources = None, REAL_PREFIX, (occurrence.event.source,)
        elif own is not None:
            transcript, prefix = own, REAL_PREFIX
            sources = (occurrence.event.source, _rel(own))
        else:
            transcript, prefix = completed_tail, COMPOSED_PREFIX
            sources = (occurrence.event.source, _rel(completed_tail))
        fixtures.append(
            StopFixture(
                name=f"{prefix}{occurrence.key}",
                evidence=_evidence(
                    occurrence, transcript=transcript, projects_root=projects_root
                ),
                expected=_declared(occurrence, _tail_reason(transcript, occurrence)),
                sources=sources,
            )
        )
    return fixtures


def _mechanical(occurrence: StopOccurrence) -> bool:
    """Does §8's table decide this stop before any tail is consulted?

    The reason a mechanical stop is given **no** tail: on 23 of 23 stop-failure
    captures the transcript's last assistant entry says `stop_sequence`, so a
    lane that read the tail first would call every API failure `unknown`. A
    fixture with no tail proves the short-circuit rather than assuming it.
    """
    return (
        occurrence.failure_error is not None
        or occurrence.end_reason in DECLARED_BY_END_REASON
        or (occurrence.end_reason is not None and bool(occurrence.prior.auto_compact_at))
    )


def _tail_reason(transcript: Path | None, occurrence: StopOccurrence) -> StopReason:
    """What §8 says a deferred stop resolves to, given the tail it was paired
    with. Declared per tail, because the pairing is the part that is ours.

    No tail at all is `unknown` — DP7's "a turn ending nobody established
    decides nothing", and the state every mechanical row would be in if the
    short-circuit did not exist.
    """
    if transcript is None:
        return StopReason.UNKNOWN
    if transcript.stem == TAIL_UNKEPT_PROMISE_STEM:
        return StopReason.INCOMPLETE
    if transcript.stem == TAIL_NO_CHANGE_STEM and _change_brief(occurrence):
        return StopReason.INCOMPLETE
    return StopReason.COMPLETED


def _change_brief(occurrence: StopOccurrence) -> bool:
    brief = (occurrence.prior.brief or "").lower()
    return any(phrase in brief for phrase in CHANGE_PHRASES)


def _own_copy(engine_session_id: str | None) -> Path | None:
    if not engine_session_id:
        return None
    for path in transcript_copies():
        if path.stem == engine_session_id:
            return path
    return None


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


# ----- the five curated compositions ------------------------------------------


def _pick(occurrences: Sequence[StopOccurrence], predicate: Callable[[StopOccurrence], bool]) -> StopOccurrence:
    """The **first** occurrence in corpus order that satisfies a predicate.

    First rather than arbitrary: the fixture set has to be byte-identical run
    to run, and "some stop that had an open ledger" is not a fixture anybody
    can find again.
    """
    for occurrence in occurrences:
        if predicate(occurrence):
            return occurrence
    raise AssertionError("no captured stop satisfies this fixture's requirement")


def _deferring(occurrence: StopOccurrence) -> bool:
    return occurrence.failure_error is None and occurrence.end_reason in (
        None,
        DEFERRING_END_REASON,
    )


def _curated(
    occurrences: Sequence[StopOccurrence],
    pty: Sequence[StopOccurrence],
    *,
    projects_root: Path,
    workspace: Path,
) -> list[StopFixture]:
    """The five rows the corpus cannot supply whole, each from real entries.

    Each one writes a transcript **into a scratch directory** out of lines a
    capture already contains — truncated, or a captured line repeated. No line
    is edited and nothing is invented; the probe files themselves are never
    written to, which `corpus_is_read_only` re-checks at the end of the run.
    """
    held = _pick(occurrences, lambda o: _deferring(o) and not o.open_ledger)
    failing = _pick(occurrences, lambda o: _deferring(o) and not o.open_ledger and o is not held)
    promised = _pick(
        occurrences,
        lambda o: _deferring(o) and not o.open_ledger and o not in (held, failing),
    )
    no_op = _pick(
        occurrences,
        lambda o: _deferring(o) and not o.open_ledger and _change_brief(o),
    )
    exited = _pick(pty, _deferring)

    tool_use_copy = _copy(TAIL_COMPLETED_STEM)
    failure_copy = _copy(TAIL_FAILURE_STEM)
    promise_copy = _copy(TAIL_UNKEPT_PROMISE_STEM)
    no_change_copy = _copy(TAIL_NO_CHANGE_STEM)

    stalled_tail = _truncate_after_tool_use(tool_use_copy, workspace / "stalled.jsonl")
    failure_tail = _repeat_failed_result(failure_copy, workspace / "failures.jsonl")

    def row(
        name: str,
        occurrence: StopOccurrence,
        transcript: Path | None,
        expected: StopReason,
        cited: str,
        *,
        exit_observed: bool = False,
    ) -> StopFixture:
        return StopFixture(
            name=COMPOSED_PREFIX + name,
            evidence=_evidence(
                occurrence,
                transcript=transcript,
                projects_root=projects_root,
                process_exit_observed=exit_observed,
            ),
            expected=expected,
            sources=(occurrence.event.source, cited),
        )

    return [
        # G-M2-3: no capture exists of `message.stop_reason = tool_use` at a
        # `Stop` — the 26 `tool_use` entries in the copies are all mid-turn. The
        # tail is a real transcript cut short at a real `tool_use` entry, which
        # is composition of captured data, not invented data.
        row(
            "g-m2-3/stalled-pending-tool",
            held,
            stalled_tail,
            StopReason.STALLED_PENDING_TOOL,
            _rel(tool_use_copy),
        ),
        # Heuristic 3: §8's "last 3 signals … on the same tool". One real
        # `is_error` result on `Bash`, repeated until the failure tail is three.
        row(
            "heuristic-3/failure-tail",
            failing,
            failure_tail,
            StopReason.INCOMPLETE,
            _rel(failure_copy),
        ),
        # Heuristic 2, captured whole: *"I'll wait …"*, and no tool call after
        # it. Only the pairing is ours.
        row(
            "heuristic-2/unkept-promise",
            promised,
            promise_copy,
            StopReason.INCOMPLETE,
            _rel(promise_copy),
        ),
        # Heuristic 4: a captured brief that asked for a change, paired with a
        # captured turn that called no change tool.
        row(
            "heuristic-4/no-op-session",
            no_op,
            no_change_copy,
            StopReason.INCOMPLETE,
            _rel(no_change_copy),
        ),
        # C13 / G-M2-2: the pidfd run observed the exit and the kernel refused
        # the code (`waitid(P_PIDFD)` → `ChildProcessError errno=10`). An
        # attached session gives an exit time and never an exit code, so the
        # honest answer is `unknown` with that sentence — never `crashed`.
        row(
            "c13/observed-process-exit",
            exited,
            None,
            StopReason.UNKNOWN,
            PIDFD_RESULTS,
            exit_observed=True,
        ),
    ]


def _truncate_after_tool_use(source: Path, target: Path) -> Path:
    """A real transcript, cut off after its last `tool_use` assistant entry."""
    lines = source.read_text(encoding="utf-8").splitlines()
    cut = max(index for index, line in enumerate(lines) if _stop_reason_of(line) == "tool_use")
    target.write_text("\n".join(lines[: cut + 1]) + "\n", encoding="utf-8")
    return target


def _repeat_failed_result(source: Path, target: Path) -> Path:
    """A real transcript with its real failed tool result repeated to three."""
    lines = source.read_text(encoding="utf-8").splitlines()
    failed = [line for line in lines if '"is_error":true' in line.replace(" ", "")]
    assert failed, f"{source.name} carries no captured is_error tool result"
    target.write_text("\n".join([*lines, failed[-1], failed[-1]]) + "\n", encoding="utf-8")
    return target


def _stop_reason_of(line: str) -> str | None:
    try:
        decoded: object = json.loads(line)
    except ValueError:
        return None
    if not isinstance(decoded, dict):
        return None
    message = decoded.get("message")
    if not isinstance(message, dict):
        return None
    value = message.get("stop_reason")
    return value if isinstance(value, str) else None


# ----- the lane ----------------------------------------------------------------


def load_stop_fixtures() -> list[StopFixture]:
    """Every stop in both corpora, plus the five curated compositions.

    The scratch directory holds the two composed transcripts for the length of
    the build and nothing else: `StopEvidence` keeps the projected tail, never
    a path, so the fixture set outlives the directory and no test can be made
    to depend on a temporary name.
    """
    corpus_one = stop_occurrences(load_corpus())
    corpus_two = stop_occurrences(load_gapfill_corpus())
    completed_tail = _copy(TAIL_COMPLETED_STEM)
    pty = [o for o in corpus_two if o.event.source.endswith("pty-hooks.jsonl")]

    with tempfile.TemporaryDirectory(prefix="shepherd-golden-") as scratch:
        workspace = Path(scratch)
        projects_root = workspace / "projects"
        projects_root.mkdir()
        fixtures = [
            *_population(
                corpus_one, projects_root=projects_root, completed_tail=completed_tail
            ),
            *_population(
                corpus_two, projects_root=projects_root, completed_tail=completed_tail
            ),
            *_curated(
                corpus_one, pty, projects_root=projects_root, workspace=workspace
            ),
        ]
    names = [fixture.name for fixture in fixtures]
    assert len(names) == len(set(names)), "two fixtures share a name"
    return fixtures


def verdict_table(fixtures: Sequence[StopFixture]) -> dict[str, dict[str, object]]:
    """The checked-in row per fixture: the whole verdict, plus its provenance.

    Keyed on the fixture name, which is the capture it came from — never on a
    session id, which is minted from a clock and is the one value that cannot
    be byte-identical run to run (M1's rule, unchanged).
    """
    table: dict[str, dict[str, object]] = {}
    for fixture in fixtures:
        verdict = classify(fixture.evidence)
        table[fixture.name] = {
            "expected": fixture.expected.value,
            "stop_reason": verdict.stop_reason.value,
            "bucket": verdict.bucket.value,
            "why": verdict.why,
            "confidence": verdict.confidence,
            "decided_by": verdict.decided_by.value,
            "next_actions": _actions(verdict),
            "waiting_on": verdict.waiting_on,
            "missing": list(verdict.missing),
            "turn_ending": fixture.evidence.tail.ending.value,
            "sources": list(fixture.sources),
        }
    return table


def _actions(verdict: Verdict) -> list[dict[str, object]]:
    return [
        {
            "text": action.text,
            "kind": action.kind.value,
            "target": action.target,
            "source": action.source.value,
        }
        for action in verdict.next_actions
    ]


def unknown_rate(fixtures: Sequence[StopFixture]) -> float:
    """P-M2-14's headline number: the share of stops nothing could classify."""
    if not fixtures:
        return 1.0
    unknown = sum(
        1 for f in fixtures if classify(f.evidence).stop_reason is StopReason.UNKNOWN
    )
    return unknown / len(fixtures)


def load_verdicts() -> dict[str, dict[str, object]]:
    decoded: object = json.loads(EXPECTED_VERDICTS.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    return {str(key): dict(value) for key, value in decoded.items() if isinstance(value, dict)}


def write_verdicts(table: Mapping[str, Mapping[str, object]]) -> None:
    """Only ever called behind `--update-golden`: never automatically (T12)."""
    EXPECTED_VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    EXPECTED_VERDICTS.write_text(
        json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
