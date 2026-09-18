"""The versioned stop record and its codec (T5, D25, ADR-M2-6).

D25 makes this log the truth `shepherd replay` reads — for 90 days, across
rule changes and code changes. Two consequences shape everything here:

* **the record is versioned, and `record_version` is its first key.** A reader
  meeting a version it does not know **skips the record and counts it**; it
  never parses optimistically (E-M2-21). A future version may have *re-meant* a
  field, and a half-parsed old record produces a confident wrong verdict, which
  is worse than no verdict at all;
* **the record carries the evidence *and* the verdict.** `replay` re-derives
  the verdict from the evidence and needs the old one to say "412 replayed, 37
  changed"; the evidence alone could not tell it what changed.

**Nothing the UI renders may read a log** (P-M2-10, D25's guardrail). The fleet
page reads columns; `replay` reads the log; the two never swap.

**No clock.** The daily file's date is derived from the record's own
`received_at`, which `core/clock.py` wrote. A date is taken by slicing the one
canonical spelling after `parse_stamp` has confirmed it *is* that spelling —
this module never formats an instant, and a stamp it cannot read becomes a
visible `unknown-date` file rather than a lost line.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from shepherd.core.clock import parse_stamp
from shepherd.core.stops import (
    STOP_RECORD_VERSION,
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopEvidence,
    StopReason,
    ToolFailure,
    ToolUseRef,
    TranscriptTail,
    TurnEnding,
    Verdict,
)
from shepherd.logs.jsonl import ReadStats, RotatingJsonlLog, scan_records

__all__ = [
    "KNOWN_RECORD_VERSIONS",
    "STOP_PREFIX",
    "UNKNOWN_DATE",
    "StopLog",
    "date_of",
    "decode_stop_evidence",
    "decode_verdict",
    "encode_stop_record",
    "read_stop_records",
]

#: The log's own subdirectory, so a second log (M4's audit, M3's pty ring) is a
#: sibling rather than an interleaving.
STOP_PREFIX = "stops"

#: Every version this build can read. One, today. An older version joins this
#: set when its decoder is written, not when it is noticed.
KNOWN_RECORD_VERSIONS: frozenset[int] = frozenset({STOP_RECORD_VERSION})

#: Where a record whose stamp this build cannot read goes. Visible on `ls`,
#: because losing the line would be the worse failure (C-M2-6).
UNKNOWN_DATE = "unknown-date"

#: The one `YYYY-MM-DD` prefix of the canonical stamp spelling.
_DATE_WIDTH = 10


def date_of(received_at: str) -> str | None:
    """The daily file's date, or `None` when the stamp is unreadable.

    `parse_stamp` decides whether the text *is* an instant — one reader, one
    format (`core/clock.py`) — and the date is then the first ten characters of
    it. Re-formatting the parsed value would make this module a second speller
    of instants, which is the defect that made every `running` session
    unreachable in M1.
    """
    if parse_stamp(received_at) is None:
        return None
    return received_at[:_DATE_WIDTH]


# ----- the codec --------------------------------------------------------------


def encode_stop_record(evidence: StopEvidence, verdict: Verdict) -> Mapping[str, object]:
    """One stop → one JSON object, `record_version` first.

    Field by field rather than `asdict`: a reflexive encoder silently changes
    the record whenever a dataclass changes, which is exactly the event
    `record_version` exists to make visible.
    """
    return {
        "record_version": STOP_RECORD_VERSION,
        "evidence": {
            "session_id": evidence.session_id,
            "engine_session_id": evidence.engine_session_id,
            "received_at": evidence.received_at,
            "mechanical": _value(evidence.mechanical),
            "mechanical_detail": evidence.mechanical_detail,
            "tail": {
                "ending": evidence.tail.ending.value,
                "last_assistant_text": evidence.tail.last_assistant_text,
                "entry_count": evidence.tail.entry_count,
                "tool_uses": [
                    {"tool_use_id": use.tool_use_id, "name": use.name, "entry_index": use.entry_index}
                    for use in evidence.tail.tool_uses
                ],
                "failures": [
                    {
                        "tool_use_id": failure.tool_use_id,
                        "name": failure.name,
                        "entry_index": failure.entry_index,
                    }
                    for failure in evidence.tail.failures
                ],
                "promise_followed_by_tool_use": evidence.tail.promise_followed_by_tool_use,
                "skipped_lines": evidence.tail.skipped_lines,
                "truncated": evidence.tail.truncated,
            },
            "tasks_total": evidence.tasks_total,
            "tasks_done": evidence.tasks_done,
            "brief": evidence.brief,
            "auto_compact_pending": evidence.auto_compact_pending,
            "quota_notice": evidence.quota_notice,
            "process_exit_observed": evidence.process_exit_observed,
            "exit_code": evidence.exit_code,
        },
        "verdict": {
            "stop_reason": verdict.stop_reason.value,
            "bucket": verdict.bucket.value,
            "why": verdict.why,
            "confidence": verdict.confidence,
            "decided_by": verdict.decided_by.value,
            "next_actions": [
                {
                    "text": action.text,
                    "kind": action.kind.value,
                    "target": action.target,
                    "source": action.source.value,
                }
                for action in verdict.next_actions
            ],
            "waiting_on": verdict.waiting_on,
            "missing": list(verdict.missing),
        },
    }


def decode_stop_evidence(record: Mapping[str, object]) -> StopEvidence:
    """One record → the evidence it carried. Raises on a shape it cannot read.

    Raising is the point: the caller counts the skip (`skipped_malformed`)
    rather than receiving a record with an invented `TurnEnding` in it.
    """
    body = _object(record["evidence"])
    tail = _object(body["tail"])
    return StopEvidence(
        record_version=_int(record["record_version"]),
        session_id=_str(body["session_id"]),
        engine_session_id=_optional_str(body["engine_session_id"]),
        received_at=_str(body["received_at"]),
        mechanical=(
            None if body["mechanical"] is None else StopReason(_str(body["mechanical"]))
        ),
        mechanical_detail=_optional_str(body["mechanical_detail"]),
        tail=TranscriptTail(
            ending=TurnEnding(_str(tail["ending"])),
            last_assistant_text=_optional_str(tail["last_assistant_text"]),
            entry_count=_int(tail["entry_count"]),
            tool_uses=tuple(
                ToolUseRef(
                    tool_use_id=_str(_object(item)["tool_use_id"]),
                    name=_str(_object(item)["name"]),
                    entry_index=_int(_object(item)["entry_index"]),
                )
                for item in _list(tail["tool_uses"])
            ),
            failures=tuple(
                ToolFailure(
                    tool_use_id=_optional_str(_object(item)["tool_use_id"]),
                    name=_optional_str(_object(item)["name"]),
                    entry_index=_int(_object(item)["entry_index"]),
                )
                for item in _list(tail["failures"])
            ),
            promise_followed_by_tool_use=_optional_bool(tail["promise_followed_by_tool_use"]),
            skipped_lines=_int(tail["skipped_lines"]),
            truncated=_bool(tail["truncated"]),
        ),
        tasks_total=_int(body["tasks_total"]),
        tasks_done=_int(body["tasks_done"]),
        brief=_optional_str(body["brief"]),
        auto_compact_pending=_bool(body["auto_compact_pending"]),
        quota_notice=_bool(body["quota_notice"]),
        process_exit_observed=_bool(body["process_exit_observed"]),
        exit_code=_optional_int(body["exit_code"]),
    )


def decode_verdict(record: Mapping[str, object]) -> Verdict:
    """The verdict as it stood when the record was written.

    `replay` needs it to say what *changed*; without it the log could only say
    how many rows it re-derived, which is the number nobody acts on.
    """
    body = _object(record["verdict"])
    return Verdict(
        stop_reason=StopReason(_str(body["stop_reason"])),
        bucket=Bucket(_str(body["bucket"])),
        why=_str(body["why"]),
        confidence=float(_number(body["confidence"])),
        decided_by=DecidedBy(_str(body["decided_by"])),
        next_actions=tuple(
            NextAction(
                text=_str(_object(item)["text"]),
                kind=NextActionKind(_str(_object(item)["kind"])),
                target=_optional_str(_object(item)["target"]),
                source=ActionSource(_str(_object(item)["source"])),
            )
            for item in _list(body["next_actions"])
        ),
        waiting_on=_optional_str(body["waiting_on"]),
        missing=tuple(_str(item) for item in _list(body["missing"])),
    )


# ----- the log ----------------------------------------------------------------


class StopLog:
    """The stop-shaped view of one `RotatingJsonlLog`.

    It **receives** the writer (ADR-M2-6): it resolves no path, so a test hands
    it a `tmp_path` and the composition root hands it the real one.
    """

    def __init__(self, log: RotatingJsonlLog) -> None:
        self._log = log

    def append(self, evidence: StopEvidence, verdict: Verdict) -> bool:
        """`False` means the line was lost — never an exception (C-M2-6).

        The log is the *second* consumer of a verdict. The first is the eight
        columns, and a log failure may never stop that write.
        """
        return self._log.append(
            encode_stop_record(evidence, verdict),
            date_of(evidence.received_at) or UNKNOWN_DATE,
        )

    def close(self) -> None:
        self._log.close()


def read_stop_records(
    directory: Path, since: str | None = None
) -> tuple[list[StopEvidence], ReadStats]:
    """Every readable stop record, with what the read had to skip.

    Several numbers, not one: a torn line, a record from a build that knows
    something this one does not, a file the read had to abandon and a partition
    `since` cannot place are different work items, and `replay` reports them
    separately because a human fixes them differently.

    **An absent or non-integer `record_version` is malformed, not version
    skew.** The split exists so the two get different fixes, and a human reading
    `0 malformed, 47 unknown version` goes looking for a decoder to write when
    the real work is corruption triage. `skipped_version` is reserved for a
    record that says which version it is and names one this build does not know.
    """
    raw, scan = scan_records(directory, STOP_PREFIX, since)
    found: list[StopEvidence] = []
    malformed = scan.skipped_malformed
    unknown_version = 0
    for record, _line in raw:
        version = record.get("record_version")
        if not isinstance(version, int) or isinstance(version, bool):
            malformed += 1
            continue
        if version not in KNOWN_RECORD_VERSIONS:
            unknown_version += 1
            continue
        try:
            found.append(decode_stop_evidence(record))
        except (KeyError, TypeError, ValueError):
            malformed += 1
    return found, ReadStats(
        records=len(found),
        skipped_malformed=malformed,
        skipped_version=unknown_version,
        unreadable_files=scan.unreadable_files,
        skipped_undated=scan.skipped_undated,
    )


# ----- the narrowings the decoder is built out of ------------------------------
#
# Each raises on the shape it cannot read, which is what turns an unreadable
# record into a counted skip instead of a decoded lie.


def _value(reason: StopReason | None) -> str | None:
    return None if reason is None else reason.value


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected an object, got {type(value).__name__}")
    narrowed: Mapping[str, object] = value
    return narrowed


def _list(value: object) -> Sequence[object]:
    if not isinstance(value, list):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    narrowed: Sequence[object] = value
    return narrowed


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected a string, got {type(value).__name__}")
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else _str(value)


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected an integer, got {type(value).__name__}")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"expected a boolean, got {type(value).__name__}")
    return value


def _optional_bool(value: object) -> bool | None:
    return None if value is None else _bool(value)
