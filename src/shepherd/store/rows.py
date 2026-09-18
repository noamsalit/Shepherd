"""Driver row → dataclass. The only place a `sqlite3.Row` is read.

Split out of `db.py` when the fold-state columns pushed it past ADR-1's 600-line
cap: the verbs are one concern (what the store can be asked to do) and the row
mapping is another (what a row means), and D33 rule 2 — a caller never sees a
driver row — is easier to police when the conversion has one home.
"""

from __future__ import annotations

import json
import sqlite3

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import NextAction
from shepherd.store.models import FleetRow, Repo, Session, TitleSource, Workspace
from shepherd.store.stops import decode_actions

__all__ = [
    "fleet_row",
    "runner_handle",
    "next_actions",
    "id_set",
    "repo",
    "repos_touched",
    "session",
    "string_list",
    "title_source",
    "workspace",
]


def title_source(raw: str) -> TitleSource:
    return "user" if raw == "user" else "engine" if raw == "engine" else "brief"


def string_list(raw: str) -> tuple[str, ...]:
    decoded: object = json.loads(raw)
    if not isinstance(decoded, list):
        return ()
    return tuple(str(item) for item in decoded)


def repos_touched(raw: str) -> tuple[str, ...]:
    return string_list(raw)


def id_set(row: sqlite3.Row, column: str) -> frozenset[str]:
    return frozenset(string_list(str(row[column])))


def next_actions(row: sqlite3.Row) -> tuple[NextAction, ...]:
    """§7's JSON column, read back whole. A record we cannot parse degrades to
    no actions and never to a raise — a row that will not render is worse than
    a row with nothing to do."""
    return decode_actions(str(row["next_actions"]))


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def runner_handle(value: object) -> RunnerHandle | None:
    """M3's `session.runner_handle`, back from its one round-trippable string.

    A row that will not parse degrades to `None` rather than raising: the only
    writer is `set_runner_handle`, whose `to_text` refuses a field carrying the
    separator, so an unparseable value is a hand-edited row — and a fleet page
    that will not render is worse than one owned row shown as handle-less,
    which is exactly the orphan cohort `owned_session_counts` already counts.
    """
    if value is None:
        return None
    try:
        return RunnerHandle.from_text(str(value))
    except ValueError:
        return None


def workspace(row: sqlite3.Row) -> Workspace:
    return Workspace(
        id=str(row["id"]),
        owner_id=str(row["owner_id"]),
        name=str(row["name"]),
        root_path=None if row["root_path"] is None else str(row["root_path"]),
        created_at=str(row["created_at"]),
        last_activity_at=None if row["last_activity_at"] is None else str(row["last_activity_at"]),
    )


def repo(row: sqlite3.Row) -> Repo:
    return Repo(
        id=str(row["id"]),
        owner_id=str(row["owner_id"]),
        workspace_id=str(row["workspace_id"]),
        name=str(row["name"]),
        root_path=str(row["root_path"]),
        git_common_dir=None if row["git_common_dir"] is None else str(row["git_common_dir"]),
        vcs_remote=None if row["vcs_remote"] is None else str(row["vcs_remote"]),
        active=bool(row["active"]),
        added_at=str(row["added_at"]),
    )


def session(row: sqlite3.Row) -> Session:
    return Session(
        id=str(row["id"]),
        owner_id=str(row["owner_id"]),
        engine_session_id=(
            None if row["engine_session_id"] is None else str(row["engine_session_id"])
        ),
        workspace_id=str(row["workspace_id"]),
        repo_id=None if row["repo_id"] is None else str(row["repo_id"]),
        origin=Origin(str(row["origin"])),
        ownership=Ownership(str(row["ownership"])),
        ephemeral=bool(row["ephemeral"]),
        depth=int(row["depth"]),
        attempt=int(row["attempt"]),
        engine=str(row["engine"]),
        brief=None if row["brief"] is None else str(row["brief"]),
        cwd=None if row["cwd"] is None else str(row["cwd"]),
        started_at=str(row["started_at"]),
        title=None if row["title"] is None else str(row["title"]),
        title_source=title_source(str(row["title_source"])),
        state=SessionState(str(row["state"])),
        last_event_at=None if row["last_event_at"] is None else str(row["last_event_at"]),
        needs_you_reason=(
            None if row["needs_you_reason"] is None else str(row["needs_you_reason"])
        ),
        model=None if row["model"] is None else str(row["model"]),
        tasks_done=int(row["tasks_done"]),
        tasks_total=int(row["tasks_total"]),
        active_subagents=int(row["active_subagents"]),
        repos_touched=repos_touched(str(row["repos_touched"])),
        pid=None if row["pid"] is None else int(row["pid"]),
        proc_start=None if row["proc_start"] is None else str(row["proc_start"]),
        ended_at=None if row["ended_at"] is None else str(row["ended_at"]),
        stop_reason=_optional_str(row["stop_reason"]),
        outcome=_optional_str(row["outcome"]),
        why=_optional_str(row["why"]),
        confidence=_optional_float(row["confidence"]),
        decided_by=_optional_str(row["decided_by"]),
        next_actions=next_actions(row),
        exit_code=_optional_int(row["exit_code"]),
        auto_compact_at=_optional_str(row["auto_compact_at"]),
        quota_notice_at=_optional_str(row["quota_notice_at"]),
        runner_handle=runner_handle(row["runner_handle"]),
        title_synced_at=_optional_str(row["title_synced_at"]),
        parent_session_id=_optional_str(row["parent_session_id"]),
        retry_of=_optional_str(row["retry_of"]),
    )


def fleet_row(row: sqlite3.Row) -> FleetRow:
    return FleetRow(
        session_id=str(row["id"]),
        engine_session_id=(
            None if row["engine_session_id"] is None else str(row["engine_session_id"])
        ),
        workspace_id=str(row["workspace_id"]),
        workspace_name=str(row["workspace_name"]),
        repo_name=None if row["repo_name"] is None else str(row["repo_name"]),
        state=SessionState(str(row["state"])),
        title=None if row["title"] is None else str(row["title"]),
        brief=None if row["brief"] is None else str(row["brief"]),
        needs_you_reason=(
            None if row["needs_you_reason"] is None else str(row["needs_you_reason"])
        ),
        tasks_done=int(row["tasks_done"]),
        tasks_total=int(row["tasks_total"]),
        active_subagents=int(row["active_subagents"]),
        last_event_at=None if row["last_event_at"] is None else str(row["last_event_at"]),
        cwd=None if row["cwd"] is None else str(row["cwd"]),
        stop_reason=_optional_str(row["stop_reason"]),
        outcome=_optional_str(row["outcome"]),
        why=_optional_str(row["why"]),
        confidence=_optional_float(row["confidence"]),
        decided_by=_optional_str(row["decided_by"]),
        next_actions=next_actions(row),
        exit_code=_optional_int(row["exit_code"]),
        runner_handle=runner_handle(row["runner_handle"]),
        title_synced_at=_optional_str(row["title_synced_at"]),
        parent_session_id=_optional_str(row["parent_session_id"]),
        depth=int(row["depth"]),
    )
