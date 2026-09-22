"""T11 — the stop lane, at the seam ADR-M2-7 exists to give.

Every test here builds the whole lane out of a `tmp_path` store, a `tmp_path`
log and a list for the publisher. No process, no composition root, no daemon:
if any of that were needed, the collaborators would not be injected and the
lane would be untestable in the way M1's `HookLane` was until it was split.

The transcripts are the captured ones under
`docs/probes/2026-09-14-schemas/transcripts/copies/`. Nothing here invents a
transcript shape.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.fold_types import SessionSnapshot
from shepherd.core.signals import Signal, SignalKind
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import DecidedBy, StopReason
from shepherd.core.stream import StreamEvent
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import StopLog, read_stop_records
from shepherd.signals import stop_lane
from shepherd.store.db import Store, open_store

REPO_ROOT = Path(__file__).resolve().parents[2]
COPIES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "transcripts" / "copies"
A_REAL_TRANSCRIPT = (
    COPIES / "-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl"
)

ENGINE_SESSION_ID = "7c27bb7f-5390-48b0-8b2e-cf4004113d09"
RECEIVED_AT = "2026-09-17T12:00:00Z"


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


def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    directory = root / "-a-lossy-slug"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{ENGINE_SESSION_ID}.jsonl").write_bytes(A_REAL_TRANSCRIPT.read_bytes())
    return root


def stop_log(directory: Path) -> StopLog:
    return StopLog(RotatingJsonlLog(directory, "stops"))


def registered(store: Store) -> str:
    """A real session row, registered the way the hook lane registers one."""
    workspace = store.create_project(name="Shepherd", description=None)
    session = store.register_session(
        engine_session_id=ENGINE_SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T11:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    return session.id


def signal(kind: SignalKind = SignalKind.TURN_STOPPED, **fields: object) -> Signal:
    return Signal(
        kind=kind,
        engine_session_id=ENGINE_SESSION_ID,
        cwd="/root/Shepherd",
        transcript_path="",
        received_at=RECEIVED_AT,
        fields=fields,
        raw_kind="opaque-to-the-lane",
    )


def prior_of(store: Store, session_id: str, **overrides: object) -> SessionSnapshot:
    snapshot = store.snapshot(session_id)
    assert snapshot is not None
    if not overrides:
        return snapshot
    import dataclasses

    return dataclasses.replace(snapshot, **overrides)  # type: ignore[arg-type]


def test_stop_signal_triggers_classification(tmp_path: Path, store: Store) -> None:
    """Five steps, one call: the record is assembled, classified, written to
    the eight columns, logged and published — with nothing constructed here."""
    session_id = registered(store)
    published = Published()
    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "logs"),
        publish=published,
    )
    assert verdict is not None
    assert verdict.stop_reason in set(StopReason)
    assert verdict.decided_by in set(DecidedBy)

    row = store.get_session(session_id)
    assert row is not None
    assert row.stop_reason == verdict.stop_reason.value
    assert row.why == verdict.why
    assert row.ended_at == RECEIVED_AT


def test_lane_runs_without_a_composition_root(tmp_path: Path, store: Store) -> None:
    """The seam ADR-M2-7 exists to give: a `tmp_path` store, a `tmp_path` log
    and a list. No daemon, no `controld`, no path resolved by the lane."""
    session_id = registered(store)
    published = Published()
    log_dir = tmp_path / "logs"
    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(log_dir),
        publish=published,
    )
    assert verdict is not None
    records, stats = read_stop_records(log_dir)
    assert stats.skipped_malformed == 0 and stats.skipped_version == 0
    assert [record.session_id for record in records] == [session_id]


def test_stop_emits_one_classified_event(tmp_path: Path, store: Store) -> None:
    """A3, r3: exactly one `session.classified`, carrying the bucket and the
    first action. It is a **second** event — the fold already emitted
    `session_stopped` before the verdict existed — and the two are
    distinguishable by `kind`, which is why this one is not named after it."""
    from shepherd.signals.fold import fold

    session_id = registered(store)
    published = Published()
    stop = signal()

    folded = fold(stop, prior_of(store, session_id), RECEIVED_AT)
    assert [event.kind for event in folded.events] == ["session_stopped"]

    verdict = stop_lane.handle_stop(
        signal=stop,
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "logs"),
        publish=published,
    )
    assert verdict is not None
    assert [event.kind for event in published.events] == [stop_lane.CLASSIFIED_EVENT]
    assert stop_lane.CLASSIFIED_EVENT != "session_stopped"

    event = published.events[0]
    assert event.session_id == session_id
    assert event.occurred_at == RECEIVED_AT
    assert event.payload["bucket"] == verdict.bucket.value
    assert event.payload["stop_reason"] == verdict.stop_reason.value
    if verdict.next_actions:
        assert event.payload["next_action"] == verdict.next_actions[0].text


class OrderRecordingLog(StopLog):
    """A real `StopLog` that notes what the row held when it was appended."""

    def __init__(self, directory: Path, store: Store, session_id: str) -> None:
        super().__init__(RotatingJsonlLog(directory, "stops"))
        self._store = store
        self._session_id = session_id
        self.reason_at_append: object = "never appended"

    def append(self, evidence: object, verdict: object) -> bool:  # type: ignore[override]
        row = self._store.get_session(self._session_id)
        self.reason_at_append = None if row is None else row.stop_reason
        return super().append(evidence, verdict)  # type: ignore[arg-type]


def test_columns_are_written_before_the_log(tmp_path: Path, store: Store) -> None:
    """C-M2-6: the columns are the first consumer of a verdict, the log the
    second. Reversed, an unwritable log directory would cost the verdict."""
    session_id = registered(store)
    log = OrderRecordingLog(tmp_path / "logs", store, session_id)
    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=log,
        publish=Published(),
    )
    assert verdict is not None
    assert log.reason_at_append == verdict.stop_reason.value


def test_log_failure_never_loses_the_verdict(tmp_path: Path, store: Store) -> None:
    """C-M2-6: an unwritable log directory. The columns are still correct, the
    loss is counted where `doctor` reads it, and nothing raises."""
    session_id = registered(store)
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "a-file").write_text("not a directory\n", encoding="utf-8")
    writer = RotatingJsonlLog(blocker / "a-file" / "stops", "stops")

    published = Published()
    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=StopLog(writer),
        publish=published,
    )
    assert verdict is not None
    row = store.get_session(session_id)
    assert row is not None
    assert row.stop_reason == verdict.stop_reason.value
    assert row.confidence == verdict.confidence
    assert writer.lost == 1, "a lost line is counted, never raised"
    assert len(published.events) == 1, "the page still repaints"


def test_second_stop_overwrites_and_both_are_logged(tmp_path: Path, store: Store) -> None:
    """E-M2-5: S18 has two stops in one session. The later verdict saw the
    later transcript, so it wins the columns — and **both** records are in the
    log, so `replay` sees the history rather than the last frame of it."""
    session_id = registered(store)
    log_dir = tmp_path / "logs"
    log = stop_log(log_dir)
    roots = projects_root(tmp_path)

    first = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=roots,
        received_at=RECEIVED_AT,
        store=store,
        stop_log=log,
        publish=Published(),
    )
    later = "2026-09-17T12:30:00Z"
    second = stop_lane.handle_stop(
        signal=signal(SignalKind.SESSION_STOPPED, end_reason="logout"),
        prior=prior_of(store, session_id),
        projects_root=roots,
        received_at=later,
        store=store,
        stop_log=log,
        publish=Published(),
    )
    assert first is not None and second is not None
    assert second.stop_reason is StopReason.LOGGED_OUT
    assert first.stop_reason is not second.stop_reason

    row = store.get_session(session_id)
    assert row is not None
    assert row.stop_reason == second.stop_reason.value
    assert row.ended_at == later

    records, _ = read_stop_records(log_dir)
    assert [record.received_at for record in records] == [RECEIVED_AT, later]


def test_observed_exit_after_a_verdict_is_ignored(tmp_path: Path, store: Store) -> None:
    """E-M2-30: a verdict that read a transcript beats one that saw a dead pid.
    Nothing is written, nothing is logged, nothing is published."""
    session_id = registered(store)
    log_dir = tmp_path / "logs"
    log = stop_log(log_dir)
    roots = projects_root(tmp_path)

    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=roots,
        received_at=RECEIVED_AT,
        store=store,
        stop_log=log,
        publish=Published(),
    )
    assert verdict is not None

    published = Published()
    ignored = stop_lane.handle_stop(
        signal=signal(SignalKind.SESSION_STOPPED),
        prior=prior_of(store, session_id),
        projects_root=roots,
        received_at="2026-09-17T13:00:00Z",
        store=store,
        stop_log=log,
        publish=published,
        process_exit_observed=True,
    )
    assert ignored is None
    assert published.events == []
    row = store.get_session(session_id)
    assert row is not None
    assert row.stop_reason == verdict.stop_reason.value
    assert row.ended_at == RECEIVED_AT

    records, _ = read_stop_records(log_dir)
    assert len(records) == 1, "an ignored exit writes no record"


def test_an_observed_exit_still_classifies_a_session_with_no_verdict(
    tmp_path: Path, store: Store
) -> None:
    """The other half of E-M2-30, stated so the guard cannot widen quietly: a
    session nothing has classified yet is exactly what the exit is for (C13)."""
    session_id = registered(store)
    verdict = stop_lane.handle_stop(
        signal=signal(SignalKind.SESSION_STOPPED),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "logs"),
        publish=Published(),
        process_exit_observed=True,
    )
    assert verdict is not None


# ----- the three "tested seam that never runs" blockers, closed -------------


def promising_transcript(tmp_path: Path) -> Path:
    """A `projects/` tree whose one transcript ends on an unkept promise.

    Composed, not captured, and the docstring says so: the *wording* is a
    captured one (`PROMISE_PHRASES`' first row, off a real last-assistant
    text), and the ordering — nothing after it — is the shape heuristic 2 is
    about. No probe session was ever driven to abandon a promise.
    """
    root = tmp_path / "projects"
    directory = root / "-a-lossy-slug"
    directory.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "type": "assistant",
            "apiBlockIndex": 0,
            "message": {
                "id": "msg_01",
                "model": "claude-haiku-4-5-20251001",
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "I'll execute these steps in order"}
                ],
            },
        }
    ]
    (directory / f"{ENGINE_SESSION_ID}.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    return root


def test_the_promise_predicate_reaches_the_tail(tmp_path: Path, store: Store) -> None:
    """BLOCKER T8-3 / T6-2. `read_tail` computes `promise_followed_by_tool_use`
    **only** when a predicate is injected, and heuristic 2 requires it to be
    `is False` — so with nothing injected the heuristic can never fire. The
    vocabulary may not live in `engines/` (ADR-M2-2's inversion), so this lane
    injects it downwards, and the record proves the value was computed."""
    session_id = registered(store)
    log_dir = tmp_path / "logs"
    stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=promising_transcript(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(log_dir),
        publish=Published(),
    )
    records, _ = read_stop_records(log_dir)
    assert len(records) == 1
    assert records[0].tail.last_assistant_text == "I'll execute these steps in order"
    assert records[0].tail.promise_followed_by_tool_use is False, (
        "no predicate was injected, so heuristic 2 can never fire"
    )


def test_the_compaction_mark_reaches_the_classifier(tmp_path: Path, store: Store) -> None:
    """BLOCKER T6-1 and the C12 trap. D24 discards the events, so the mark
    reaches the stop through T10's column — and the death path is the one
    carrying a session-ending reason. A benign compacted turn carries none."""
    session_id = registered(store)
    roots = projects_root(tmp_path)
    marked = prior_of(store, session_id, auto_compact_at="2026-09-17T11:58:00Z")

    benign = stop_lane.handle_stop(
        signal=signal(SignalKind.TURN_STOPPED),
        prior=marked,
        projects_root=roots,
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "benign"),
        publish=Published(),
    )
    assert benign is not None
    assert benign.stop_reason is not StopReason.CONTEXT_EXHAUSTED

    death = stop_lane.handle_stop(
        signal=signal(SignalKind.SESSION_STOPPED, end_reason="other"),
        prior=marked,
        projects_root=roots,
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "death"),
        publish=Published(),
    )
    assert death is not None
    assert death.stop_reason is StopReason.CONTEXT_EXHAUSTED


def test_the_quota_mark_reaches_the_classifier(tmp_path: Path, store: Store) -> None:
    """The other fact D24 would discard: a quota notice arrived and no turn
    followed it (§8's `quota_paused`)."""
    session_id = registered(store)
    verdict = stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id, quota_notice_at="2026-09-17T11:59:30Z"),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "logs"),
        publish=Published(),
    )
    assert verdict is not None
    assert verdict.stop_reason is StopReason.QUOTA_PAUSED


def test_the_session_ending_reason_reaches_the_classifier(
    tmp_path: Path, store: Store
) -> None:
    """The four mechanical endings §8 names. Without the neutral projection and
    this thread, every one of them is a tested row that never runs."""
    session_id = registered(store)
    roots = projects_root(tmp_path)
    expected = {
        "prompt_input_exit": StopReason.USER_EXITED,
        "clear": StopReason.CLEARED,
        "logout": StopReason.LOGGED_OUT,
        "resume": StopReason.RESUMED_ELSEWHERE,
    }
    for value, reason in expected.items():
        verdict = stop_lane.handle_stop(
            signal=signal(SignalKind.SESSION_STOPPED, end_reason=value),
            prior=prior_of(store, session_id),
            projects_root=roots,
            received_at=RECEIVED_AT,
            store=store,
            stop_log=stop_log(tmp_path / value),
            publish=Published(),
        )
        assert verdict is not None
        assert verdict.stop_reason is reason, value
        assert verdict.decided_by is DecidedBy.MECHANICAL, value
        assert verdict.confidence == 1.0, value


# ----- the lane's own discipline -------------------------------------------


def test_stop_lane_constructs_nothing() -> None:
    """It is not a composition root: no store is opened, no log is built, no
    path literal is resolved and no clock is read. `daemons/controld.py` sits
    at ADR-1's cap and Task 18 owns its growth, not this module."""
    import ast

    source = (
        REPO_ROOT / "src" / "shepherd" / "signals" / "stop_lane.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    forbidden = {
        "open_store",
        "RotatingJsonlLog",
        "StopLog",
        "Path",
        "open",
        "utc_now",
        "stamp",
        "now",
        "mkdir",
    }
    assert called & forbidden == set(), sorted(called & forbidden)

    docstrings = {
        ast.get_docstring(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
    }
    path_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
        and node.value.startswith("/")
    ]
    assert path_literals == [], path_literals
    assert len(source.splitlines()) <= 600


def test_the_transcript_is_read_exactly_once(
    tmp_path: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-M2-1: assembled once, at the stop. The record is what `replay` reads
    back, so a second read would be a second (and later) truth."""
    from shepherd.engines.claude_code import transcript_tail as tail_module

    calls: list[Path] = []
    real = tail_module.read_tail

    def counting(path: Path, *args: object, **kwargs: object) -> object:
        calls.append(path)
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("shepherd.engines.claude_code.evidence.read_tail", counting)

    session_id = registered(store)
    stop_lane.handle_stop(
        signal=signal(),
        prior=prior_of(store, session_id),
        projects_root=projects_root(tmp_path),
        received_at=RECEIVED_AT,
        store=store,
        stop_log=stop_log(tmp_path / "logs"),
        publish=Published(),
    )
    assert len(calls) == 1, calls


def test_the_lane_names_no_engine_event(tmp_path: Path, store: Store) -> None:
    """K13, at the one module that sits between the adapter and the rules. A
    printed constant counts; the boundary suite scans this file too."""
    from shepherd.engines.claude_code.events import ALL_HOOK_EVENT_NAMES

    source = (
        REPO_ROOT / "src" / "shepherd" / "signals" / "stop_lane.py"
    ).read_text(encoding="utf-8")
    import ast

    literals = [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    docstrings = {
        ast.get_docstring(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
    }
    printed = [text for text in literals if text not in docstrings]
    for name in ALL_HOOK_EVENT_NAMES:
        assert not any(name in text.split() for text in printed), name


# ----- the one new call site (T11's allowed scope) --------------------------


def hook_frame(event: str, received_at: str = RECEIVED_AT, **extra: object) -> object:
    from shepherd.core.frames import Frame

    body: dict[str, object] = {
        "session_id": ENGINE_SESSION_ID,
        "transcript_path": "",
        "cwd": "/root/Shepherd",
        "hook_event_name": event,
    }
    body.update(extra)
    return Frame(
        payload=json.dumps(body).encode("utf-8") + b"\n",
        received_at=received_at,
        peer_pid=None,
    )


def test_hook_lane_routes_a_stop_into_the_stop_lane(tmp_path: Path, store: Store) -> None:
    """The one call site. `HookLane` calls `handle_stop`; it does not contain
    it (ADR-M2-7), and the collaborators it hands over are the ones it was
    given — it constructs none of them either."""
    from shepherd.signals.hook_lane import HookLane

    published = Published()
    log_dir = tmp_path / "logs"
    lane = HookLane(
        store,
        published,
        stop_log=stop_log(log_dir),
        projects_root=projects_root(tmp_path),
    )
    lane.apply(hook_frame("UserPromptSubmit", prompt="do the thing"))
    lane.apply(hook_frame("Stop"))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    assert session.state is SessionState.STOPPED
    assert session.stop_reason is not None, "the stop was never classified"

    kinds = [event.kind for event in published.events]
    assert kinds.count(stop_lane.CLASSIFIED_EVENT) == 1
    assert kinds.count("session_stopped") == 1, "the fold's event still fires first"
    assert kinds.index("session_stopped") < kinds.index(stop_lane.CLASSIFIED_EVENT)

    records, _ = read_stop_records(log_dir)
    assert [record.session_id for record in records] == [session.id]


def test_hook_lane_without_a_stop_log_behaves_exactly_as_before(
    tmp_path: Path, store: Store
) -> None:
    """T18-3: `HookLane.__init__` grows **defaulted** parameters, so every M1
    call site keeps working and nothing classifies until T18 wires the log."""
    from shepherd.signals.hook_lane import HookLane

    published = Published()
    lane = HookLane(store, published)
    lane.apply(hook_frame("Stop"))

    session = store.get_session_by_engine_id(ENGINE_SESSION_ID)
    assert session is not None
    assert session.state is SessionState.STOPPED
    assert session.stop_reason is None
    assert [event.kind for event in published.events] == ["session_stopped"]
