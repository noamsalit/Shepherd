"""`StopEvidence` assembly (T6) — the one place the three sources meet.

The stop's own metadata, the session's **folded counters**, and the neutral
transcript tail become one immutable record (ADR-M2-1). That record is what
goes to the stop log verbatim and what `replay` reads back, so the transcript
is read **exactly once**, here, at the stop — and `replay` still works months
later on a machine where the engine's project directory has been cleared.

Three properties this module is held to:

* **It reads no clock.** `received_at` is a parameter, always. A timestamp
  format owned by a reader and no writer is exactly the defect that failed M1's
  verification — every `running` session silently demoted, 444 tests green.
* **It writes nothing.** It opens one transcript, for reading, and touches no
  path it was not handed (principle 4, C-M2-6).
* **It projects no engine spelling into the record.** The record crosses into
  `signals/`, so both its field names and its values are neutral. The one
  engine value it reads is the neutral `failure_note` the normaliser already
  projected — read by a **named literal key, one at a time** (K12), never as a
  whole mapping.

The subtlety worth stating: the hook lane hands the adapter back its own
neutral projection, and the engine's spelling never leaves `engines/`.

**Four arguments are required rather than defaulted, deliberately.** The two
fold marks, the session-ending reason and the promise predicate all come from
outside this module, and defaulting any of them would mean `context_exhausted`,
`quota_paused`, every session-ending reason, or heuristic 2 silently never
firing — a tested seam that never runs, which is the exact defect the r3 review
found in the stop path twice. Required keyword arguments turn that into a type
error at the one call site that has to thread them, and T11's `handle_stop` is
that call site (BLOCKER T6-1 and T8-3, both closed there).

**`promise` is injected rather than imported** for the reason `read_tail` takes
it at all: the *ordering* fact — did a tool call follow the last message? — is
a transcript shape and belongs here, while *what counts as a promise* is a rule
whose vocabulary lives in `signals/heuristics.py`. Importing it would invert
ADR-M2-2's direction and put the classifier's words on the adapter's import
path; a rule hiding in an adapter is D9.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.fold_types import SessionSnapshot
from shepherd.core.signals import Signal
from shepherd.core.stops import STOP_RECORD_VERSION, StopEvidence, TranscriptTail, TurnEnding
from shepherd.engines.claude_code.stop_map import mechanical_reason
from shepherd.engines.claude_code.transcript_tail import locate_transcript, read_tail

__all__ = ["build_stop_evidence"]

#: The one neutral key this module reads out of `Signal.fields`. A named
#: literal, read once: a computed key fails closed everywhere it matters (K12),
#: and this module holds itself to the same rule because what it produces is
#: what crosses the boundary.
_FAILURE_NOTE = "failure_note"

#: The tail a session with no readable transcript gets. Every field is the
#: honest "nothing was established", and `ending=ABSENT` is what stops the
#: completeness split from running on a record that cannot support it
#: (E-M2-12).
_NO_TAIL = TranscriptTail(
    ending=TurnEnding.ABSENT,
    last_assistant_text=None,
    entry_count=0,
    tool_uses=(),
    failures=(),
    promise_followed_by_tool_use=None,
    skipped_lines=0,
    truncated=False,
)


def build_stop_evidence(
    *,
    signal: Signal,
    prior: SessionSnapshot,
    projects_root: Path,
    received_at: str,
    end_reason: str | None,
    auto_compact_pending: bool,
    quota_notice: bool,
    promise: Callable[[str], bool],
    process_exit_observed: bool = False,
    exit_code: int | None = None,
) -> tuple[StopEvidence, tuple[Anomaly, ...]]:
    """One stop -> one immutable record, plus everything it had to degrade on."""
    anomalies: list[Anomaly] = []

    tail = _NO_TAIL
    transcript = _transcript_path(signal, prior, projects_root)
    if transcript is None:
        anomalies.append(
            Anomaly(
                kind=AnomalyKind.TRANSCRIPT_TAIL_ABSENT,
                detail=(
                    "no transcript file for this session; the turn ending could not"
                    " be established"
                ),
                engine_session_id=signal.engine_session_id,
            )
        )
    else:
        tail, tail_anomalies = read_tail(transcript, promise=promise)
        anomalies.extend(tail_anomalies)

    mechanical = mechanical_reason(
        failure_error=_failure_note(signal),
        end_reason=end_reason,
        ending=tail.ending,
        auto_compact_pending=auto_compact_pending,
        quota_notice=quota_notice,
        process_exit_observed=process_exit_observed,
        exit_code=exit_code,
    )
    anomalies.extend(mechanical.anomalies)

    record = StopEvidence(
        record_version=STOP_RECORD_VERSION,
        session_id=prior.session_id,
        engine_session_id=prior.engine_session_id or signal.engine_session_id,
        received_at=received_at,
        mechanical=mechanical.reason,
        mechanical_detail=mechanical.detail,
        tail=tail,
        tasks_total=prior.tasks_total,
        tasks_done=prior.tasks_done,
        brief=prior.brief,
        auto_compact_pending=auto_compact_pending,
        quota_notice=quota_notice,
        process_exit_observed=process_exit_observed,
        exit_code=exit_code,
    )
    return record, tuple(anomalies)


def _failure_note(signal: Signal) -> str | None:
    """The neutral projection of the engine's stop-failure error.

    One named key, read once. The value is still the engine's word, which is
    why the table that interprets it lives in this package and not in
    `signals/` (ADR-M2-2).
    """
    value = signal.fields.get(_FAILURE_NOTE)
    return value if isinstance(value, str) and value else None


def _transcript_path(
    signal: Signal, prior: SessionSnapshot, projects_root: Path
) -> Path | None:
    """The path the engine announced, or the one the session id globs to.

    Never the reversed project-directory slug: it is lossy and hash-suffixed
    past 200 UTF-16 units, so two cwds can share one directory and the session
    id is the only key.
    """
    announced = signal.transcript_path
    if announced:
        candidate = Path(announced)
        if candidate.is_file():
            return candidate
    engine_session_id = prior.engine_session_id or signal.engine_session_id
    if not engine_session_id:
        return None
    return locate_transcript(projects_root, engine_session_id)
