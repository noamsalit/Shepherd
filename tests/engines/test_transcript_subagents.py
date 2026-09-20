"""T13 — the subagent rollup, read from the transcript on demand.

A subagent has **no structured state field anywhere** (C20): `.meta.json` carries
its type and description, the `.jsonl` carries its timestamps, and its *state*
exists only as the `<status>` tag of a `<task-notification>` in the parent
transcript, or — for workflow agents — in `journal.jsonl` / `wf_<runId>.json`.

The three real sessions under
`docs/probes/2026-09-14-schemas/transcripts/copies/` are the fixtures: two
Agent-tool subagents and one workflow run. They are read-only evidence. The
cases the captures do not contain (a depth-2 spawn, a missing agent transcript,
a half-written trailing line, a workflow still in flight) are built under
`tmp_path` from the documented field list.
"""

from __future__ import annotations

import json
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.engines.claude_code.transcript import (
    SubagentRow,
    locate_transcript,
    read_subagents,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "transcripts" / "copies"
SLUG = PROJECTS / "-tmp-shp-schemas-tx-blIf90-work"

AGENT_SESSION = "0141fab3-8bf8-4b69-be1f-89552ccfce5d"
BG_SESSION = "7515f181-14c5-4540-9107-4f1d1267cf83"
WORKFLOW_SESSION = "518c280f-3791-4571-ae9a-f002c8f3b33c"

AGENT_ID = "a4388d337bf8a9397"
WORKFLOW_AGENT_ID = "aff491fda998b3fe0"

#: The `.meta.json` shape, from data-schemas §"Subagent transcript and `.meta.json`".
META_SHAPE: dict[str, object] = {
    "agentType": "general-purpose",
    "description": "probe child",
    "toolUseId": "toolu_01AjU2TvSydb1THCnRCcYCLQ",
    "spawnDepth": 1,
    "requestShape": "background",
    "requestNonInteractive": True,
}


def by_id(rows: list[SubagentRow]) -> dict[str, SubagentRow]:
    return {row.agent_id: row for row in rows}


def build_session(root: Path, session_id: str, main_lines: list[str]) -> Path:
    slug = root / "-tmp-fixture-work"
    (slug / session_id / "subagents").mkdir(parents=True, exist_ok=True)
    transcript = slug / f"{session_id}.jsonl"
    transcript.write_text("".join(line + "\n" for line in main_lines), encoding="utf-8")
    return transcript


def notification(agent_id: str, status: str) -> str:
    return json.dumps(
        {
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": "2026-09-14T15:07:13.811Z",
            "sessionId": "fixture",
            "content": (
                f"<task-notification>\n<task-id>{agent_id}</task-id>\n"
                f"<status>{status}</status>\n</task-notification>"
            ),
        }
    )


def agent_entry(agent_id: str, entry_type: str, timestamp: str) -> str:
    return json.dumps(
        {
            "isSidechain": True,
            "agentId": agent_id,
            "type": entry_type,
            "timestamp": timestamp,
            "sessionId": "fixture",
        }
    )


def write_agent(
    transcript: Path, agent_id: str, meta: dict[str, object], entries: list[str]
) -> None:
    folder = transcript.parent / transcript.stem / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if entries:
        (folder / f"agent-{agent_id}.jsonl").write_text(
            "".join(line + "\n" for line in entries), encoding="utf-8"
        )


# ----- the real captures ------------------------------------------------------


def test_reads_agent_meta_json() -> None:
    rows, anomalies = read_subagents(SLUG / f"{AGENT_SESSION}.jsonl")

    assert [row.agent_id for row in rows] == [AGENT_ID]
    row = rows[0]
    assert row.agent_type == "general-purpose"
    assert row.description == "probe child"
    assert row.source == "agent"
    assert row.started_at == "2026-09-14T15:07:12.183Z"
    assert row.last_activity_at is not None
    assert row.last_activity_at > row.started_at
    assert anomalies == ()


def test_state_from_task_notification_status() -> None:
    """C20 — the only place an Agent-tool subagent's state is written down."""
    rows, _ = read_subagents(SLUG / f"{AGENT_SESSION}.jsonl")
    assert rows[0].state == "done"

    bg_rows, _ = read_subagents(SLUG / f"{BG_SESSION}.jsonl")
    assert [row.state for row in bg_rows] == ["done"]


def test_reads_workflow_journal() -> None:
    rows, anomalies = read_subagents(SLUG / f"{WORKFLOW_SESSION}.jsonl")

    assert [row.agent_id for row in rows] == [WORKFLOW_AGENT_ID]
    row = rows[0]
    assert row.agent_type == "workflow-subagent"
    assert row.description == "ping"
    assert row.source == "workflow"
    assert row.state == "done"  # journal `result`, and wf_<runId>.json `state: done`
    assert anomalies == ()


def test_tail_filters_by_entry_type(tmp_path: Path) -> None:
    """E25 — 44.4 % of entries are neither user nor assistant. Filter by `type`."""
    transcript = build_session(tmp_path, "sess-tail", [notification("agent-x", "completed")])
    write_agent(
        transcript,
        "agent-x",
        META_SHAPE,
        [
            agent_entry("agent-x", "user", "2026-09-14T15:07:12.183Z"),
            agent_entry("agent-x", "assistant", "2026-09-14T15:07:13.509Z"),
            agent_entry("agent-x", "attachment", "2026-09-14T15:09:99.000Z"),
        ],
    )

    rows, _ = read_subagents(transcript)

    assert rows[0].started_at == "2026-09-14T15:07:12.183Z"
    assert rows[0].last_activity_at == "2026-09-14T15:07:13.509Z"


def test_malformed_trailing_line_is_skipped(tmp_path: Path) -> None:
    """D25 — a daemon killed mid-write leaves exactly one truncated line."""
    transcript = build_session(tmp_path, "sess-torn", [notification("agent-y", "completed")])
    folder = transcript.parent / transcript.stem / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agent-agent-y.meta.json").write_text(json.dumps(META_SHAPE), encoding="utf-8")
    (folder / "agent-agent-y.jsonl").write_text(
        agent_entry("agent-y", "user", "2026-09-14T15:07:12.183Z")
        + "\n"
        + agent_entry("agent-y", "assistant", "2026-09-14T15:07:13.509Z")
        + '\n{"isSidechain":true,"type":"assist',
        encoding="utf-8",
    )

    rows, anomalies = read_subagents(transcript)

    assert rows[0].last_activity_at == "2026-09-14T15:07:13.509Z"
    assert len(anomalies) == 1


def test_missing_agent_transcript_is_counted_not_raised(tmp_path: Path) -> None:
    """E26 — a compaction subagent's announced transcript never existed."""
    transcript = build_session(tmp_path, "sess-gone", [])
    write_agent(transcript, "agent-z", META_SHAPE, [])

    rows, anomalies = read_subagents(transcript)

    assert [row.agent_id for row in rows] == ["agent-z"]
    assert rows[0].started_at is None
    assert rows[0].last_activity_at is None
    assert len(anomalies) >= 1
    assert any("agent-z" in anomaly.detail for anomaly in anomalies)
    # BLOCKER T13-1: a transcript that was announced and never written is not a
    # torn JSONL line, and `doctor` must be able to tell the two apart.
    kinds = [anomaly.kind for anomaly in anomalies]
    assert AnomalyKind.MISSING_SUBAGENT_TRANSCRIPT in kinds
    assert AnomalyKind.MALFORMED_PAYLOAD not in kinds


def test_unparsed_state_is_unknown_and_counted(tmp_path: Path) -> None:
    """Principle 5/E28 — an unreadable state is unknown, counted, never guessed."""
    transcript = build_session(tmp_path, "sess-odd", [notification("agent-q", "levitating")])
    write_agent(
        transcript,
        "agent-q",
        META_SHAPE,
        [agent_entry("agent-q", "user", "2026-09-14T15:07:12.183Z")],
    )
    write_agent(
        transcript,
        "agent-r",
        META_SHAPE,
        [agent_entry("agent-r", "user", "2026-09-14T15:07:12.183Z")],
    )

    rows, anomalies = read_subagents(transcript)
    found = by_id(rows)

    assert found["agent-q"].state == "unknown"
    assert found["agent-r"].state == "unknown"  # no notification at all
    # BLOCKER T13-1: two different unknowns, named apart. A status word we do
    # not map is an unmapped notice; a subagent whose state is written down
    # nowhere at all is its own condition.
    unmapped = [
        anomaly for anomaly in anomalies if anomaly.kind is AnomalyKind.UNMAPPED_NOTICE
    ]
    unwritten = [
        anomaly
        for anomaly in anomalies
        if anomaly.kind is AnomalyKind.SUBAGENT_STATE_UNKNOWN
    ]
    assert [anomaly.detail for anomaly in unmapped] == [
        "subagent agent-q: unrecognised notification status 'levitating'"
    ]
    assert len(unwritten) == 1
    assert "not readable" in unwritten[0].detail and "agent-r" in unwritten[0].detail


def test_last_notification_wins(tmp_path: Path) -> None:
    """Metadata entries are re-appended; the reader takes the **last** occurrence."""
    transcript = build_session(
        tmp_path,
        "sess-again",
        [notification("agent-m", "completed"), notification("agent-m", "levitating")],
    )
    write_agent(
        transcript,
        "agent-m",
        META_SHAPE,
        [agent_entry("agent-m", "user", "2026-09-14T15:07:12.183Z")],
    )

    rows, _ = read_subagents(transcript)

    assert rows[0].state == "unknown"


def test_nested_spawn_depth_2_is_flattened_with_parent(tmp_path: Path) -> None:
    """Depth-2 agents are stored flat in the same folder; both rows come back."""
    transcript = build_session(
        tmp_path,
        "sess-nested",
        [notification("agent-parent", "completed"), notification("agent-child", "completed")],
    )
    write_agent(
        transcript,
        "agent-parent",
        META_SHAPE,
        [agent_entry("agent-parent", "user", "2026-09-14T15:07:12.183Z")],
    )
    child_meta = dict(META_SHAPE)
    child_meta["spawnDepth"] = 2
    child_meta["parentAgentId"] = "agent-parent"
    child_meta["description"] = "nested child"
    write_agent(
        transcript,
        "agent-child",
        child_meta,
        [agent_entry("agent-child", "user", "2026-09-14T15:07:20.000Z")],
    )

    rows, _ = read_subagents(transcript)
    found = by_id(rows)

    assert set(found) == {"agent-parent", "agent-child"}
    assert found["agent-child"].description == "nested child"
    assert found["agent-child"].state == "done"


def test_workflow_started_without_result_is_running(tmp_path: Path) -> None:
    """A live run has a journal and no `wf_<runId>.json` at all."""
    transcript = build_session(tmp_path, "sess-wf", [])
    run_dir = transcript.parent / transcript.stem / "subagents" / "workflows" / "wf_abc12345-def"
    run_dir.mkdir(parents=True)
    (run_dir / "agent-inflight.meta.json").write_text(
        json.dumps(
            {
                "agentType": "workflow-subagent",
                "description": "ping",
                "workflowPhase": "Ping",
                "spawnDepth": 1,
                "requestShape": "foreground",
                "requestNonInteractive": True,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "agent-inflight.jsonl").write_text(
        agent_entry("inflight", "user", "2026-09-14T15:09:57.241Z") + "\n",
        encoding="utf-8",
    )
    (run_dir / "journal.jsonl").write_text(
        '{"type":"launched"}\n'
        '{"type":"started","agentId":"inflight","label":"ping","phase":"Ping"}\n',
        encoding="utf-8",
    )

    rows, anomalies = read_subagents(transcript)

    assert [row.agent_id for row in rows] == ["inflight"]
    assert rows[0].state == "running"
    assert rows[0].source == "workflow"
    assert anomalies == ()


def test_locate_transcript_globs_not_slug() -> None:
    """§Project directory slug rule — the slug is lossy and hash-suffixed."""
    found = locate_transcript(PROJECTS, AGENT_SESSION)

    assert found == SLUG / f"{AGENT_SESSION}.jsonl"
    assert locate_transcript(PROJECTS, "00000000-0000-0000-0000-000000000000") is None
    # D24's glob, taken literally, matches nothing: the transcripts are one
    # directory down, and the subagents deeper still.
    assert list(PROJECTS.glob("*.jsonl")) == []


def test_no_session_directory_is_empty_not_an_error(tmp_path: Path) -> None:
    """A session that never spawned a subagent has no `<sessionId>/` directory."""
    transcript = tmp_path / "slug" / "sess-bare.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("", encoding="utf-8")

    rows, anomalies = read_subagents(transcript)

    assert rows == []
    assert anomalies == ()
