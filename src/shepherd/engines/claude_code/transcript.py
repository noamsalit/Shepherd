"""Subagent rollup, read from the transcript on demand (T13, §7 line 609).

A subagent has **no structured state field anywhere** (C20). `.meta.json` gives
its type and description, its own `.jsonl` gives its timestamps, and its *state*
has to be derived:

* Agent-tool subagents: from the `<status>` tag of a `<task-notification>` in the
  **parent** transcript — the notification arrives as a `queue-operation` and
  again as a `user` entry, and it is re-appended, so the **last** occurrence wins.
* Workflow subagents: from `journal.jsonl` (a `started` with no `result` is
  still running) or from `workflows/wf_<runId>.json` once the run completes —
  that file does not exist while the run is in flight.

Four shapes of the real world this reader has to survive, each from a capture:

* the transcript is **append-only JSONL and the last line may be half-written**
  (D25) — a malformed line is skipped and counted, never raised;
* a `SubagentStop.agent_transcript_path` **may not exist** — the compaction
  subagent's did not (E26);
* **44.4 % of entries are neither `user` nor `assistant`**, so a tail is taken by
  entry `type` and never by line count (E25);
* the project-directory slug is **lossy and hash-suffixed past 200 UTF-16
  units**, so `locate_transcript` globs for the session id and never reverses it.

Read on demand, for the one session that was opened — never for every session on
every render (§7). This module only ever reads.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shepherd.core.anomalies import Anomaly, AnomalyKind

SubagentState = Literal["running", "done", "unknown"]
SubagentSource = Literal["agent", "workflow"]

#: The entry types that count as activity (E25). Everything else — `attachment`,
#: `system`, `queue-operation`, the metadata entries — is bookkeeping.
ACTIVITY_ENTRY_TYPES: frozenset[str] = frozenset({"user", "assistant"})

SUBAGENTS_DIRNAME = "subagents"
WORKFLOWS_DIRNAME = "workflows"
AGENT_META_GLOB = "agent-*.meta.json"
META_SUFFIX = ".meta.json"
AGENT_PREFIX = "agent-"
JOURNAL_NAME = "journal.jsonl"
RUN_DIR_GLOB = "wf_*"

#: The one `<status>` value observed on a finished Agent-tool subagent.
COMPLETED_STATUS = "completed"
#: `workflowProgress[].state` for a finished workflow agent.
WORKFLOW_DONE_STATE = "done"

_TASK_ID = re.compile(r"<task-id>(.*?)</task-id>", re.DOTALL)
_STATUS = re.compile(r"<status>(.*?)</status>", re.DOTALL)


@dataclass(frozen=True)
class SubagentRow:
    """One line of the fleet's third tier (§12 line 1870)."""

    agent_id: str
    agent_type: str
    description: str
    started_at: str | None
    last_activity_at: str | None
    state: SubagentState
    source: SubagentSource


def locate_transcript(projects_root: Path, engine_session_id: str) -> Path | None:
    """`projects/*/<sessionId>.jsonl` — by glob, never by reversing the slug.

    Two cwds can share one project directory (the slug is lossy), and past 200
    UTF-16 units it carries a hash suffix, so the session id is the only key.
    """
    matches = sorted(projects_root.glob(f"*/{engine_session_id}.jsonl"))
    return matches[0] if matches else None


def read_subagents(transcript_path: Path) -> tuple[list[SubagentRow], tuple[Anomaly, ...]]:
    """Every subagent of one session: Agent-tool and workflow, in one list."""
    session_dir = transcript_path.parent / transcript_path.stem
    anomalies: list[Anomaly] = []
    states = _notification_states(transcript_path, anomalies)

    rows = _agent_rows(session_dir, states, anomalies)
    rows += _workflow_rows(session_dir, anomalies)
    return sorted(rows, key=lambda row: row.agent_id), tuple(anomalies)


# ----- Agent-tool subagents ---------------------------------------------------


def _agent_rows(
    session_dir: Path, states: dict[str, str], anomalies: list[Anomaly]
) -> list[SubagentRow]:
    folder = session_dir / SUBAGENTS_DIRNAME
    if not folder.is_dir():
        return []

    rows: list[SubagentRow] = []
    for meta_path in sorted(folder.glob(AGENT_META_GLOB)):
        agent_id = meta_path.name[len(AGENT_PREFIX) : -len(META_SUFFIX)]
        meta = _read_json_object(meta_path, anomalies)
        if meta is None:
            continue
        started, last = _activity_window(meta_path.with_name(f"{AGENT_PREFIX}{agent_id}.jsonl"),
                                         anomalies)
        rows.append(
            SubagentRow(
                agent_id=agent_id,
                agent_type=_string(meta.get("agentType")) or "",
                description=_string(meta.get("description")) or "",
                started_at=started,
                last_activity_at=last,
                state=_agent_state(agent_id, states, anomalies),
                source="agent",
            )
        )
    return rows


def _agent_state(
    agent_id: str, states: dict[str, str], anomalies: list[Anomaly]
) -> SubagentState:
    status = states.get(agent_id)
    if status == COMPLETED_STATUS:
        return "done"
    # Two different unknowns, named apart (BLOCKER T13-1): a status word we saw
    # and could not map is an unmapped notice; a subagent the transcript says
    # nothing about at all is a condition of its own, and `doctor` has to be
    # able to tell them apart to be worth reading.
    if status is None:
        anomalies.append(
            _anomaly(
                AnomalyKind.SUBAGENT_STATE_UNKNOWN,
                f"subagent {agent_id}: state not readable from the transcript",
            )
        )
        return "unknown"
    anomalies.append(
        _anomaly(
            AnomalyKind.UNMAPPED_NOTICE,
            f"subagent {agent_id}: unrecognised notification status {status!r}",
        )
    )
    return "unknown"


def _notification_states(transcript_path: Path, anomalies: list[Anomaly]) -> dict[str, str]:
    """`<task-id>` → the **last** `<status>` seen for it (entries are re-appended)."""
    states: dict[str, str] = {}
    for entry in _entries(transcript_path, anomalies):
        for text in _notification_texts(entry):
            task_ids = _TASK_ID.findall(text)
            statuses = _STATUS.findall(text)
            if task_ids and statuses:
                states[task_ids[0].strip()] = statuses[0].strip()
    return states


def _notification_texts(entry: dict[str, object]) -> list[str]:
    """The two carriers of a `<task-notification>`: `content`, and a `user` entry."""
    found: list[str] = []
    content = entry.get("content")
    if isinstance(content, str) and "<task-notification>" in content:
        found.append(content)
    message = entry.get("message")
    if isinstance(message, dict):
        inner: object = message.get("content")
        if isinstance(inner, str) and "<task-notification>" in inner:
            found.append(inner)
        elif isinstance(inner, list):
            for part in inner:
                if isinstance(part, dict):
                    text = part.get("content")
                    if isinstance(text, str) and "<task-notification>" in text:
                        found.append(text)
    return found


# ----- workflow subagents -----------------------------------------------------


def _workflow_rows(session_dir: Path, anomalies: list[Anomaly]) -> list[SubagentRow]:
    root = session_dir / SUBAGENTS_DIRNAME / WORKFLOWS_DIRNAME
    if not root.is_dir():
        return []

    rows: list[SubagentRow] = []
    for run_dir in sorted(path for path in root.glob(RUN_DIR_GLOB) if path.is_dir()):
        journal = _journal_states(run_dir / JOURNAL_NAME, anomalies)
        summary = _run_summary_states(
            session_dir / WORKFLOWS_DIRNAME / f"{run_dir.name}.json", anomalies
        )
        for meta_path in sorted(run_dir.glob(AGENT_META_GLOB)):
            agent_id = meta_path.name[len(AGENT_PREFIX) : -len(META_SUFFIX)]
            meta = _read_json_object(meta_path, anomalies)
            if meta is None:
                continue
            started, last = _activity_window(
                meta_path.with_name(f"{AGENT_PREFIX}{agent_id}.jsonl"), anomalies
            )
            rows.append(
                SubagentRow(
                    agent_id=agent_id,
                    agent_type=_string(meta.get("agentType")) or "",
                    description=_string(meta.get("description")) or "",
                    started_at=started,
                    last_activity_at=last,
                    state=summary.get(agent_id) or journal.get(agent_id) or "unknown",
                    source="workflow",
                )
            )
    return rows


def _journal_states(path: Path, anomalies: list[Anomaly]) -> dict[str, SubagentState]:
    """`started` without a `result` is still running — the live-run case."""
    states: dict[str, SubagentState] = {}
    for entry in _entries(path, anomalies):
        agent_id = _string(entry.get("agentId"))
        if agent_id is None:
            continue
        kind = _string(entry.get("type"))
        if kind == "started":
            states.setdefault(agent_id, "running")
        elif kind == "result":
            states[agent_id] = "done"
    return states


def _run_summary_states(path: Path, anomalies: list[Anomaly]) -> dict[str, SubagentState]:
    """`wf_<runId>.json` — written only after the run completes."""
    summary = _read_json_object(path, anomalies, required=False)
    if summary is None:
        return {}
    progress: object = summary.get("workflowProgress")
    if not isinstance(progress, list):
        return {}
    states: dict[str, SubagentState] = {}
    for item in progress:
        if not isinstance(item, dict):
            continue
        agent_id = _string(item.get("agentId"))
        state = _string(item.get("state"))
        if agent_id is None or state is None:
            continue
        states[agent_id] = "done" if state == WORKFLOW_DONE_STATE else "running"
    return states


# ----- shared reading ---------------------------------------------------------


def _activity_window(path: Path, anomalies: list[Anomaly]) -> tuple[str | None, str | None]:
    """First and last **activity** timestamp, filtered by entry `type` (E25)."""
    if not path.is_file():
        anomalies.append(
            _anomaly(
                AnomalyKind.MISSING_SUBAGENT_TRANSCRIPT,
                f"subagent transcript {path.name} does not exist",
            )
        )
        return None, None

    stamps = [
        stamp
        for entry in _entries(path, anomalies)
        if _string(entry.get("type")) in ACTIVITY_ENTRY_TYPES
        for stamp in [_string(entry.get("timestamp"))]
        if stamp is not None
    ]
    return (stamps[0], stamps[-1]) if stamps else (None, None)


def _entries(path: Path, anomalies: list[Anomaly]) -> list[dict[str, object]]:
    """Every parsable JSONL object. A torn trailing line is counted, not raised."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    found: list[dict[str, object]] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            decoded: object = json.loads(line)
        except ValueError as error:
            anomalies.append(
                _anomaly(
                    AnomalyKind.MALFORMED_PAYLOAD,
                    f"{path.name}:{number}: unparsable jsonl line: {error}",
                )
            )
            continue
        if isinstance(decoded, dict):
            found.append({str(key): value for key, value in decoded.items()})
    return found


def _read_json_object(
    path: Path, anomalies: list[Anomaly], required: bool = True
) -> dict[str, object] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        if required:
            anomalies.append(
                _anomaly(AnomalyKind.MALFORMED_PAYLOAD, f"{path.name} is unreadable")
            )
        return None
    try:
        decoded: object = json.loads(raw)
    except ValueError as error:
        anomalies.append(
            _anomaly(AnomalyKind.MALFORMED_PAYLOAD, f"{path.name}: unparsable json: {error}")
        )
        return None
    if not isinstance(decoded, dict):
        anomalies.append(_anomaly(AnomalyKind.MALFORMED_PAYLOAD, f"{path.name}: not an object"))
        return None
    return {str(key): value for key, value in decoded.items()}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _anomaly(kind: AnomalyKind, detail: str) -> Anomaly:
    return Anomaly(kind=kind, detail=detail, engine_session_id=None)
