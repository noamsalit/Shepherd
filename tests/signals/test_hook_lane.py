"""The hook lane's own composition: frame → signal → fold → store → stream.

ADR-1 caps `daemons/*` at 150 lines and forbids logic there, so the two rules
the fold deliberately does not own — registration on the first event of any kind
(D47) and re-binding the repo when a session changes directory — live here,
where they can be tested without a process. The golden lane (T12) already proves
this shape over 429 real captured events; this is the production path it was
proving.

**BLOCKER T11-3 is closed here**, at the seam the blocker named. `fold()` is pure
by contract, so a changed path *outside* the session's own cwd — the cross-repo
case `repos_touched` exists for — could never be attributed inside it: resolving
an arbitrary path to a repo runs git. The composition root can, and this is it.

Every payload below is the captured shape from
`docs/probes/2026-09-14-schemas/hooks/live/S09_perm_dontAsk_write_outside/`:
`PostToolUse` with `tool_name: "Write"` and `tool_input.file_path` — the one
capture in the corpus that writes outside the session's own directory.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

import pytest
from signals.conftest import GitWorld

from shepherd.core.frames import Frame
from shepherd.core.states import SessionState
from shepherd.core.stops import StopReason
from shepherd.core.stream import StreamEvent
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import StopLog
from shepherd.signals.hook_lane import HookLane
from shepherd.signals.stop_lane import CLASSIFIED_EVENT
from shepherd.store.db import Store, open_store

RECEIVED_AT = "2026-09-16T10:00:30Z"
ENGINE_SESSION_ID = "5d1202ea-3765-459d-8299-8630c710c50d"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


class Published:
    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    def __call__(self, event: StreamEvent) -> int:
        self.events.append(event)
        return len(self.events)


def frame(payload: dict[str, object], received_at: str = RECEIVED_AT) -> Frame:
    return Frame(
        payload=json.dumps(payload).encode("utf-8") + b"\n",
        received_at=received_at,
        peer_pid=None,
    )


def write_payload(cwd: str, file_path: str) -> dict[str, object]:
    """The S09 capture's shape, with the two paths the test is about."""
    return {
        "session_id": ENGINE_SESSION_ID,
        "cwd": cwd,
        "permission_mode": "dontAsk",
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": "x"},
        "tool_use_id": "toolu_012CQgKZPPKKLQx9nH3Qjkbi",
    }


def test_a_frame_registers_its_session_and_folds_it(store: Store, git_world: GitWorld) -> None:
    """D47: registration is keyed on the absence of a row, never on a kind — a
    session already running when hooks were installed never announces itself."""
    published = Published()
    lane = HookLane(store=store, publish=published)

    lane.apply(frame(write_payload(str(git_world.main), str(git_world.main / "README.md"))))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    assert session.cwd == str(git_world.main)
    assert session.state is SessionState.RUNNING
    assert session.last_event_at == RECEIVED_AT
    assert session.repo_id is not None
    assert [event.session_id for event in published.events] == [session.id]


def test_a_changed_path_inside_the_session_repo_marks_that_repo(
    store: Store, git_world: GitWorld
) -> None:
    """§7's ordinary case, still decided by the pure fold — not by this lane.

    (C9 is about the *source* — `PostToolUse` paths instead of `FileChanged` —
    not about which repo a path is attributed to.)
    """
    lane = HookLane(store=store, publish=Published())
    lane.apply(frame(write_payload(str(git_world.main), str(git_world.main / "src" / "app.py"))))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    snapshot = store.snapshot(session.id)
    assert snapshot is not None
    assert snapshot.repo_id is not None
    assert snapshot.repos_touched == (snapshot.repo_id,)


def test_a_changed_path_in_another_repo_is_attributed(
    store: Store, git_world: GitWorld
) -> None:
    """BLOCKER T11-3: the cross-repo case, which is what the column exists for.

    The session's cwd is one repo and the write lands in a *different* one. The
    pure fold leaves it alone (resolving an arbitrary path runs git), so before
    this lane existed `repos_touched` was empty at M1 for exactly the case it
    was added for. Here the path is resolved through the same `bind_cwd_to_repo`
    the registration used, and a second `FoldDelta` carries the result through
    the one writer (D37).
    """
    lane = HookLane(store=store, publish=Published())
    victim = git_world.noremote / "outside.txt"

    lane.apply(frame(write_payload(str(git_world.main), str(victim))))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    snapshot = store.snapshot(session.id)
    assert snapshot is not None
    assert snapshot.repo_id is not None

    # §7's column is "repo ids **accumulated**" from the paths that changed, so
    # it is the *other* repo that is marked here — the session's own repo had
    # nothing written to it by this event. (Not C9: C9 rules only on the
    # *source*, that `FileChanged` never fires for agent edits so `PostToolUse`
    # paths are read instead. It says nothing about which repos get marked.)
    assert len(snapshot.repos_touched) == 1
    foreign = snapshot.repos_touched[0]
    assert foreign != snapshot.repo_id

    # …and it is a real `repo` row, bound by D48's key, not an invented id.
    bound = store.find_repo_by_common_dir(str(git_world.noremote / ".git"))
    assert bound is not None
    assert bound.id == foreign


def test_repos_touched_accumulates_across_two_repos(store: Store, git_world: GitWorld) -> None:
    """§7's worked example, which no test covered: `('A',)` → `('A', 'B')`.

    The spec's own `session` row spans two repos — "it started in
    `reporting-service` and has since edited `ox-ai-agent` too" — and the column
    is defined as *accumulated*. Two events, two repos, and the second must not
    replace the first: one write inside the session's own repo (attributed by
    the pure fold) and one into a different real repo (attributed here, at the
    composition root, because resolving an arbitrary path runs git).
    """
    lane = HookLane(store=store, publish=Published())

    lane.apply(frame(write_payload(str(git_world.main), str(git_world.main / "README.md"))))
    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    first = store.snapshot(session.id)
    assert first is not None
    own = first.repo_id
    assert own is not None
    assert first.repos_touched == (own,)

    lane.apply(frame(write_payload(str(git_world.main), str(git_world.noremote / "outside.txt"))))
    second = store.snapshot(session.id)
    assert second is not None

    foreign = store.find_repo_by_common_dir(str(git_world.noremote / ".git"))
    assert foreign is not None
    assert second.repos_touched == tuple(sorted((own, foreign.id)))
    assert second.repo_id == own  # accumulating a second repo never rebinds the first


def test_an_unattributable_path_is_left_alone_not_guessed_at(
    store: Store, git_world: GitWorld
) -> None:
    """Principle 5: a path in no repo at all adds nothing, and raises nothing."""
    lane = HookLane(store=store, publish=Published())
    lane.apply(frame(write_payload(str(git_world.main), str(git_world.plain / "loose.txt"))))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    snapshot = store.snapshot(session.id)
    assert snapshot is not None
    assert snapshot.repos_touched == ()


def test_a_malformed_payload_is_counted_never_raised(store: Store) -> None:
    """§8: an unreadable payload is a counter, not a traceback in a hook."""
    lane = HookLane(store=store, publish=Published())
    lane.apply(Frame(payload=b"{not json", received_at=RECEIVED_AT, peer_pid=None))

    counts = store.list_anomaly_counts()
    assert sum(counts.values()) == 1
    assert store.list_sessions() == []


def test_a_cwd_change_rebinds_the_repo(store: Store, git_world: GitWorld) -> None:
    """The second rule the pure fold does not own: `CwdChanged` runs git."""
    lane = HookLane(store=store, publish=Published())
    lane.apply(frame(write_payload(str(git_world.main), str(git_world.main / "README.md"))))
    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    first = store.snapshot(session.id)
    assert first is not None

    lane.apply(
        frame(
            {
                "session_id": ENGINE_SESSION_ID,
                "cwd": str(git_world.main),
                "hook_event_name": "CwdChanged",
                "new_cwd": str(git_world.noremote),
            }
        )
    )

    moved = store.snapshot(session.id)
    assert moved is not None
    assert moved.cwd == str(git_world.noremote)
    assert moved.repo_id is not None
    assert moved.repo_id != first.repo_id


# ----- the additive widening (T18-3) ---------------------------------------
# `HookLane.__init__` gained `stop_log` and `projects_root`, both defaulted, so
# every M1 call site keeps working. "Keeps working" is asserted differentially:
# the same frames go through a two-argument lane and a fully wired one, and the
# only difference allowed is the classification the wired one performs.

#: The session id of the captured transcript below — `locate_transcript` globs
#: by it, so the two must match or the fallback finds nothing.
STOP_SESSION_ID = "7c27bb7f-5390-48b0-8b2e-cf4004113d09"
A_REAL_TRANSCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docs/probes/2026-09-14-schemas/transcripts/copies"
    / "-tmp-shp-schemas-tx-blIf90-work"
    / f"{STOP_SESSION_ID}.jsonl"
)


def stop_payload(cwd: str) -> dict[str, object]:
    """§Stop's captured shape (`S10_effort_sonnet/events.jsonl`)."""
    return {
        "session_id": STOP_SESSION_ID,
        "transcript_path": f"{cwd}/never-written.jsonl",
        "cwd": cwd,
        "prompt_id": "a95c9922-3b49-44f2-8906-ef313239b6c1",
        "permission_mode": "default",
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message": "DONE",
        "background_tasks": [],
        "session_crons": [],
    }


def prompt_payload(cwd: str) -> dict[str, object]:
    """§UserPromptSubmit's captured shape — the frame that registers the row."""
    return {
        "session_id": STOP_SESSION_ID,
        "cwd": cwd,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "build the composition root",
    }


def planted_projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "engine-config" / "projects"
    directory = root / "-a-lossy-slug"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{STOP_SESSION_ID}.jsonl").write_bytes(A_REAL_TRANSCRIPT.read_bytes())
    return root


def observable(row: object) -> dict[str, object]:
    """The session row minus the three generated ids, which differ per store."""
    assert row is not None
    fields = dict(asdict(row))  # type: ignore[call-overload]
    for generated in ("id", "workspace_id", "repo_id"):
        fields.pop(generated, None)
    return fields


def test_hook_lane_without_a_stop_log_behaves_exactly_as_before(
    store: Store, tmp_path: Path, git_world: GitWorld
) -> None:
    """The M1 call site, unchanged, against the same frames the wired lane sees.

    Two lanes, two stores, one pair of captured frames. The two-argument lane
    must leave a row indistinguishable from M1's — every stop column `None`,
    the same events published, and nothing written to disk anywhere — while the
    wired lane classifies. Asserting only the first half would pass against a
    lane that had quietly stopped classifying for everyone.
    """
    cwd = str(git_world.main)
    frames = [frame(prompt_payload(cwd)), frame(stop_payload(cwd))]

    m1_published = Published()
    m1_lane = HookLane(store=store, publish=m1_published)  # exactly M1's call
    for one in frames:
        m1_lane.apply(one)

    wired_store = open_store(tmp_path / "wired" / "shepherd.db")
    try:
        wired_published = Published()
        log_dir = tmp_path / "logs"
        wired_lane = HookLane(
            store=wired_store,
            publish=wired_published,
            stop_log=StopLog(RotatingJsonlLog(log_dir, "stops")),
            projects_root=planted_projects_root(tmp_path),
        )
        for one in frames:
            wired_lane.apply(one)

        m1_row = observable(store.get_session_by_engine_id(STOP_SESSION_ID))
        wired_row = observable(wired_store.get_session_by_engine_id(STOP_SESSION_ID))
    finally:
        wired_store.close()

    # The wired lane really did classify — otherwise everything below is vacuous.
    assert wired_row["stop_reason"] is not None
    assert list((log_dir / "stops").rglob("*.jsonl")) != []

    # …and the two-argument lane is M1's: no verdict, in any of the stop columns,
    # and identical to the wired row in every column that is not one of them.
    unwritten: dict[str, object] = {
        "stop_reason": None, "outcome": None, "why": None, "confidence": None,
        "decided_by": None, "exit_code": None, "next_actions": (),
    }
    for column, empty in unwritten.items():
        assert m1_row[column] == empty, f"{column} was written without a stop log"
    assert m1_row == {**wired_row, **unwritten}

    # …and the events it published differ by exactly the classification event.
    def seen(published: Published) -> list[tuple[str, object, str]]:
        return [(event.kind, event.payload, event.occurred_at) for event in published.events]

    assert seen(m1_published) != []
    assert CLASSIFIED_EVENT not in [kind for kind, _, _ in seen(m1_published)]
    assert seen(m1_published) == [row for row in seen(wired_published) if row[0] != CLASSIFIED_EVENT]


# ----- the quota mark is not a latch (BLOCKER T10-2, option 1 applied) ------


def quota_notice_payload(cwd: str) -> dict[str, object]:
    """§Notification's captured envelope, with one of the three quota values of
    `notification_type` from the binary enum capture
    (`docs/probes/2026-09-14-schemas/hooks/binary/enums.json`). Only the *type*
    is read (G-M2-1), which is why no message field is asserted anywhere."""
    return {
        "session_id": STOP_SESSION_ID,
        "transcript_path": f"{cwd}/never-written.jsonl",
        "cwd": cwd,
        "prompt_id": "190ccd82-3a5c-48e4-b9e2-3d288b7fbd37",
        "hook_event_name": "Notification",
        "message": "anything at all",
        "notification_type": "quota_auto_resume_fired",
    }


def test_a_quota_notice_does_not_latch_every_later_stop_as_quota_paused(
    store: Store, tmp_path: Path, git_world: GitWorld
) -> None:
    """T10-2, applied: `TURN_STOPPED` clears `quota_notice_at`.

    The whole session, through the production lane: a notice arrives, the turn
    it interrupted ends — and **that** stop is a real `quota_paused` — and then
    an ordinary later turn ends. Before the clear, the second stop read the mark
    the first one left behind and the row said `quota_paused` for the rest of
    the session's life, which D18 costs as a parked work item.
    """
    cwd = str(git_world.main)
    lane = HookLane(
        store=store,
        publish=Published(),
        stop_log=StopLog(RotatingJsonlLog(tmp_path / "logs", "stops")),
        projects_root=planted_projects_root(tmp_path),
    )

    lane.apply(frame(prompt_payload(cwd), "2026-09-17T12:00:00Z"))
    lane.apply(frame(quota_notice_payload(cwd), "2026-09-17T12:00:10Z"))
    lane.apply(frame(stop_payload(cwd), "2026-09-17T12:00:20Z"))

    interrupted = store.get_session_by_engine_id(STOP_SESSION_ID)
    assert interrupted is not None
    # The mark reached the classifier for the turn it was actually about…
    assert interrupted.stop_reason == StopReason.QUOTA_PAUSED.value
    # …and the turn ending consumed it: the mark is the one `CLEARED_STAMP`
    # writes, exactly as `auto_compact_at` beside it already was.
    consumed = store.snapshot(interrupted.id)
    assert consumed is not None
    assert not consumed.quota_notice_at, "TURN_STOPPED left the quota mark standing"

    lane.apply(frame(prompt_payload(cwd), "2026-09-17T12:01:00Z"))
    lane.apply(frame(stop_payload(cwd), "2026-09-17T12:01:20Z"))

    later = store.get_session_by_engine_id(STOP_SESSION_ID)
    assert later is not None
    assert later.stop_reason != StopReason.QUOTA_PAUSED.value, (
        "the quota mark latched: every stop after the first notice reads quota_paused"
    )
