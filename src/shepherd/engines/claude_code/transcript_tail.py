"""The transcript tail reader (T3) — the one place the engine's on-disk format
is read for classification, projected into the neutral `TranscriptTail`.

A separate module from `transcript.py` (~340 lines, owns the subagent rollup):
principle 6 and ADR-1's 600-line cap. Both read the same files; they answer
different questions.

**Read-only, and bounded.** This runs on `controld`'s *single* ingest thread —
one `ingest` thread calls `HookLane.apply` for every frame — against user
transcripts of thousands of entries. A full-file scan per stop delays the next
hook's frame, and "the observer never harms the observed" (principle 4,
C-M2-6) is the one clause M2 may not trade. So: read the last `TAIL_BYTES`,
discard the first partial line, **then** filter by entry type and take the last
`TAIL_ENTRIES`. When the window was truncated the tail says so and is counted —
a shorter tail degrades a heuristic; a silent one invents a fact.

The eight rules, each from a capture:

1. **Filter by entry `type` first, then take the last 20.** Only ~56 % of lines
   are `user`/`assistant`, and metadata is *re-appended* so it clusters in the
   tail (E25, E-M2-15). A line-count tail returns bookkeeping.
2. **Skip malformed lines and count them**; never raise (D25, E-M2-11).
3. **Group `assistant` entries by message id** before reading text: one API
   message is split across entries, one per content block, with an increasing
   `apiBlockIndex` (E-M2-14).
4. **Resolve the ending from the last group that decided something**, walking
   back over nulls (E-M2-13). Anything unrecognised is `OTHER`, counted (DP7).
5. **Exclude client-generated entries** from the ending — no API call was made,
   so no turn ended (E-M2-18).
6. **Collect tool calls** with their id, name and entry index (heuristic 4).
7. **Collect failed tool results**, paired back to their call by id; an
   unpairable one keeps `name=None` and is counted (E-M2-17).
8. **`promise_followed_by_tool_use`** is the ordering fact only. The promise
   *vocabulary* is T8's, and arrives as an injected predicate — without one
   there was no promise to judge and the field is `None`.

`stop_reason` appears here, and that is not a D46 violation: D46 says the
`Stop` **hook payload** has no such field (absent from 26 captures and from the
CLI's own schema). The transcript's `message.stop_reason` is a different object
on a different surface and is exactly what D46 says to read instead.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.stops import ToolFailure, ToolUseRef, TranscriptTail, TurnEnding
from shepherd.engines.claude_code.transcript import ACTIVITY_ENTRY_TYPES, locate_transcript

__all__ = ["TAIL_BYTES", "TAIL_ENTRIES", "locate_transcript", "read_tail"]

#: §8's "last ~20 `user`/`assistant` entries", counted **after** the type filter.
TAIL_ENTRIES = 20

#: A4's bounded window. The largest captured single entry is 410 665 bytes
#: (§Transcript JSONL: "one line of 410665 bytes appeared whole"), so this is
#: deliberately not large enough to hold every possible line — which is why the
#: truncation counter is not decorative.
TAIL_BYTES = 256 * 1024

#: ADR-M2-3's narrowing. Two of the engine's four observed spellings collapse
#: into `OTHER`; the mapping is a table so a fifth spelling is a row, not a
#: branch. The keys are the **transcript's** vocabulary and live here, in the
#: adapter, for exactly that reason.
_ENDINGS: Mapping[str, TurnEnding] = {
    "end_turn": TurnEnding.ENDED_TURN,
    "tool_use": TurnEnding.HELD_TOOL_CALL,
    "max_tokens": TurnEnding.HIT_TOKEN_CAP,
}

#: A client-generated assistant entry: no API call was made, so nothing ended a
#: turn (E-M2-18). Two captures, both carrying `stop_sequence`.
_CLIENT_GENERATED_MODEL = "<synthetic>"

_ASSISTANT = "assistant"
_USER = "user"
_MESSAGE = "message"


@dataclass(frozen=True)
class _Entry:
    """One parsed activity entry, with the index it sat at in the window."""

    index: int
    kind: str
    message: Mapping[str, object]

    @property
    def blocks(self) -> Sequence[Mapping[str, object]]:
        content = self.message.get("content")
        if not isinstance(content, list):
            return ()
        return [block for block in content if isinstance(block, Mapping)]


def read_tail(
    path: Path,
    limit: int = TAIL_ENTRIES,
    max_bytes: int = TAIL_BYTES,
    promise: Callable[[str], bool] | None = None,
) -> tuple[TranscriptTail, tuple[Anomaly, ...]]:
    """One transcript -> one neutral `TranscriptTail`. Never raises (P-M2-7)."""
    anomalies: list[Anomaly] = []
    window, truncated = _window(path, max_bytes, anomalies)
    if truncated:
        anomalies.append(
            _anomaly(
                AnomalyKind.TRANSCRIPT_TAIL_TRUNCATED,
                f"{path.name}: read the last {max_bytes} bytes; the tail may be short",
            )
        )

    entries = _activity_entries(window, path.name, anomalies)
    skipped = sum(
        1 for anomaly in anomalies if anomaly.kind is AnomalyKind.MALFORMED_PAYLOAD
    )
    kept = entries[-limit:] if limit >= 0 else entries

    groups = _assistant_groups(kept)
    ending = _ending(groups, path.name, anomalies)
    tool_uses = _tool_uses(kept)
    failures = _failures(kept, tool_uses, path.name, anomalies)

    return (
        TranscriptTail(
            ending=ending,
            last_assistant_text=_last_text(groups),
            entry_count=len(kept),
            tool_uses=tool_uses,
            failures=failures,
            promise_followed_by_tool_use=_promise_kept(groups, kept, promise),
            skipped_lines=skipped,
            truncated=truncated,
        ),
        tuple(anomalies),
    )


# ----- the bounded read -------------------------------------------------------


def _window(path: Path, max_bytes: int, anomalies: list[Anomaly]) -> tuple[list[str], bool]:
    """The last `max_bytes` as whole lines, plus whether the file was longer.

    A mid-line seek leaves a partial first line. That is **not** a torn write,
    so it is discarded without counting: confusing the two would make every
    bounded read report a corrupt transcript.
    """
    try:
        size = path.stat().st_size
    except OSError as error:
        anomalies.append(
            _anomaly(AnomalyKind.TRANSCRIPT_TAIL_ABSENT, f"{path.name}: {error}")
        )
        return [], False
    if not path.is_file():
        anomalies.append(
            _anomaly(
                AnomalyKind.TRANSCRIPT_TAIL_ABSENT,
                f"{path.name}: not a readable file",
            )
        )
        return [], False

    start = max(0, size - max_bytes) if max_bytes >= 0 else 0
    try:
        with open(path, "rb") as handle:
            if start:
                handle.seek(start)
            raw = handle.read(max_bytes if max_bytes >= 0 else -1)
    except OSError as error:
        anomalies.append(
            _anomaly(AnomalyKind.TRANSCRIPT_TAIL_ABSENT, f"{path.name}: {error}")
        )
        return [], False

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start and lines:
        lines = lines[1:]
    return lines, bool(start)


def _activity_entries(
    lines: list[str], name: str, anomalies: list[Anomaly]
) -> list[_Entry]:
    """Rules 1 and 2: parse, count what will not parse, then filter by type."""
    entries: list[_Entry] = []
    for number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded: object = json.loads(stripped)
        except ValueError as error:
            anomalies.append(
                _anomaly(
                    AnomalyKind.MALFORMED_PAYLOAD,
                    f"{name}: unparsable jsonl line in the tail window: {error}",
                )
            )
            continue
        if not isinstance(decoded, Mapping):
            continue
        kind = decoded.get("type")
        if not isinstance(kind, str) or kind not in ACTIVITY_ENTRY_TYPES:
            continue
        message = decoded.get(_MESSAGE)
        entries.append(
            _Entry(
                index=number,
                kind=kind,
                message=message if isinstance(message, Mapping) else {},
            )
        )
    return entries


# ----- rule 3: one API message is many entries --------------------------------


def _assistant_groups(entries: list[_Entry]) -> list[list[_Entry]]:
    """Consecutive `assistant` entries sharing a message id, in order.

    Grouped by id rather than by adjacency *and* kept in arrival order, so the
    "last group" is the last message the model actually produced even when a
    `user` tool result interleaves between two of its blocks (7c27bb7f does
    exactly that: blocks 0, 1 and 2 of one message straddle two results).
    """
    groups: list[list[_Entry]] = []
    index_of: dict[str, int] = {}
    for entry in entries:
        if entry.kind != _ASSISTANT:
            continue
        message_id = entry.message.get("id")
        key = message_id if isinstance(message_id, str) else f"#{entry.index}"
        position = index_of.get(key)
        if position is None:
            index_of[key] = len(groups)
            groups.append([entry])
        else:
            groups[position].append(entry)
    return groups


def _is_client_generated(group: list[_Entry]) -> bool:
    return any(
        entry.message.get("model") == _CLIENT_GENERATED_MODEL for entry in group
    )


# ----- rules 4 and 5: what ended the turn -------------------------------------


def _ending(
    groups: list[list[_Entry]], name: str, anomalies: list[Anomaly]
) -> TurnEnding:
    for group in reversed(groups):
        if _is_client_generated(group):
            continue
        raw = _declared_ending(group)
        if raw is None:
            continue
        mapped = _ENDINGS.get(raw)
        if mapped is not None:
            return mapped
        anomalies.append(
            _anomaly(
                AnomalyKind.STOP_UNMAPPED_VALUE,
                f"{name}: the transcript's turn ending {raw!r} has no member; counted as other",
            )
        )
        return TurnEnding.OTHER
    anomalies.append(
        _anomaly(
            AnomalyKind.TRANSCRIPT_TAIL_ABSENT,
            f"{name}: no entry in the window ended a turn",
        )
    )
    return TurnEnding.ABSENT


def _declared_ending(group: list[_Entry]) -> str | None:
    """The last non-null ending this message declared. A `null` decides nothing
    — a lone `thinking` block carries one (E-M2-13)."""
    for entry in reversed(group):
        value = entry.message.get("stop_reason")
        if isinstance(value, str) and value:
            return value
    return None


def _last_text(groups: list[list[_Entry]]) -> str | None:
    """Rule 3: the concatenation of the `text` blocks of the **last** group."""
    if not groups:
        return None
    pieces = [
        str(block.get("text"))
        for entry in groups[-1]
        for block in entry.blocks
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    joined = "".join(pieces)
    return joined if joined else None


# ----- rules 6 and 7: what the turn did and what failed -----------------------


def _tool_uses(entries: list[_Entry]) -> tuple[ToolUseRef, ...]:
    return tuple(
        ToolUseRef(
            tool_use_id=str(block.get("id")),
            name=str(block.get("name")),
            entry_index=entry.index,
        )
        for entry in entries
        if entry.kind == _ASSISTANT
        for block in entry.blocks
        if block.get("type") == "tool_use"
        and isinstance(block.get("id"), str)
        and isinstance(block.get("name"), str)
    )


def _failures(
    entries: list[_Entry],
    tool_uses: tuple[ToolUseRef, ...],
    name: str,
    anomalies: list[Anomaly],
) -> tuple[ToolFailure, ...]:
    by_id = {use.tool_use_id: use.name for use in tool_uses}
    failures: list[ToolFailure] = []
    for entry in entries:
        if entry.kind != _USER:
            continue
        for block in entry.blocks:
            if block.get("type") != "tool_result" or block.get("is_error") is not True:
                continue
            raw_id = block.get("tool_use_id")
            call_id = raw_id if isinstance(raw_id, str) else None
            tool_name = by_id.get(call_id) if call_id is not None else None
            if tool_name is None:
                anomalies.append(
                    _anomaly(
                        AnomalyKind.TOOL_RESULT_UNPAIRED,
                        f"{name}: failed tool result {call_id!r} has no call in the window",
                    )
                )
            failures.append(
                ToolFailure(tool_use_id=call_id, name=tool_name, entry_index=entry.index)
            )
    return tuple(failures)


# ----- rule 8: the ordering fact, not the vocabulary --------------------------


def _promise_kept(
    groups: list[list[_Entry]],
    entries: list[_Entry],
    promise: Callable[[str], bool] | None,
) -> bool | None:
    """`None` when there was no promise to judge — which includes "nobody asked".

    Judged at the **last group that made a promise**, not at the last group
    outright: if the promise had to be the final message then "a later entry
    carries a tool call" would be unsatisfiable by construction and the field
    could only ever be `False`.

    The predicate is injected because the promise *vocabulary* belongs to the
    heuristics (T8) and this module may not grow one: a reader that decided
    what counts as a promise would be a rule hiding in an adapter.
    """
    if promise is None:
        return None
    for group in reversed(groups):
        text = _last_text_of(group)
        if text is None or not promise(text):
            continue
        after = max(entry.index for entry in group)
        return any(
            entry.index > after
            and entry.kind == _ASSISTANT
            and any(block.get("type") == "tool_use" for block in entry.blocks)
            for entry in entries
        )
    return None


def _last_text_of(group: list[_Entry]) -> str | None:
    pieces = [
        str(block.get("text"))
        for entry in group
        for block in entry.blocks
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    return "".join(pieces) or None


def _anomaly(kind: AnomalyKind, detail: str) -> Anomaly:
    return Anomaly(kind=kind, detail=detail, engine_session_id=None)
