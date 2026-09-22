"""The golden-fixture lane's loader and replay harness (T12, §14 lane 1).

**The fixtures ARE Claude Code.** Nothing here mocks the engine: every byte fed
to `parse_hook_payload` is a `payload` object captured from a real hook's stdin
in `docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl`, and every
timestamp is that capture's own `_epoch` — which is exactly what C8 says the
receiver supplies, so the lane tests receiver stamping without inventing a clock.

The corpus is **read-only evidence**: a test that disagrees with a capture is a
wrong test, or a wrong fold. Never edit a capture to make one pass.

Two orderings are built from the same 429 envelopes:

* **sequential** — the sessions in the order they first appear, each session's
  events in `_epoch` order. This is how the corpus was recorded.
* **interleaved** — all 429 envelopes merge-sorted on `_epoch` across session
  ids (G3). The 50 sessions are near-sequential but not entirely: three of them
  are re-entered after another session has produced events, so this is a *real*
  ordering of real events rather than invented contention.

**T17 added the second corpus and the stops inside both.** `load_gapfill_corpus`
reads `gap-fill/`, which is the only source of `SessionEnd.reason = resume` and
`= logout`, of the compaction pair, and — through a **second glob, for a second
filename** — of the pidfd run's observed-process-exit evidence.
`stop_occurrences` replays either corpus and hands back every stop with the
prior state the live lane would have passed to `handle_stop`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from shepherd.core.fold_types import FoldDelta, SessionSnapshot
from shepherd.core.signals import MalformedPayload, Signal
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.engines.claude_code.normalise import parse_hook_payload
from shepherd.signals.fold import advance, fold
from shepherd.signals.stop_lane import STOP_KINDS
from shepherd.store.db import Store

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_ROOT = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"
CORPUS_ROOT = PROBE_ROOT / "hooks" / "live"
EXPECTED_TABLE = Path(__file__).resolve().parent / "expected" / "sessions.json"

#: The measured shape of the corpus, asserted by the tests that guard it.
EXPECTED_EVENT_COUNT = 429
EXPECTED_SESSION_COUNT = 50
EXPECTED_SCENARIOS_WITH_EVENTS = 53

# ----- the second corpus (T17) ------------------------------------------------

#: The gap-fill probes: the run that went looking for what the first corpus did
#: not contain. It is the **only** source of `SessionEnd.reason = resume` and
#: `= logout`, of `PreCompact`/`PostCompact`, and of the kill-mid-compaction
#: sequence `context_exhausted` rests on.
GAPFILL_ROOT = PROBE_ROOT / "gap-fill"

#: **Two globs, and the second one is the point (A5, r3).** `pty-hooks.jsonl`
#: is not `hooks.jsonl`: the plan's original single glob silently matched none
#: of the pidfd run's six captures, which is how C13's observed-process-exit
#: evidence came to be invisible. Every glob here is asserted to match an exact
#: expected count — never `> 0`, because a glob that matches nothing is exactly
#: what an evidence gap looks like from the inside.
GAPFILL_HOOK_GLOBS: tuple[str, ...] = ("*/hooks.jsonl", "pidfd-pty-*/pty-hooks.jsonl")

#: The measured shape of the second corpus. 239 lines over 10 files: 9 scenario
#: `hooks.jsonl` and the 1 `pidfd-pty-*/pty-hooks.jsonl` the first glob misses.
EXPECTED_GAPFILL_FILE_COUNT = 10
EXPECTED_GAPFILL_PTY_FILE_COUNT = 1
EXPECTED_GAPFILL_EVENT_COUNT = 239
EXPECTED_GAPFILL_SESSION_COUNT = 39

#: 23 of the 239 lines are the probe harness's **own** `MARKER` records —
#: `{"_event": "MARKER", "label": …, "payload": {}}`. They carry no
#: `hook_event_name` and are not hook captures at all, so the adapter refuses
#: them. Counted rather than filtered: a torn capture and a harness marker are
#: two different facts, and only one of them is a defect (principle 5).
GAPFILL_MARKER_LABEL = "MARKER"
EXPECTED_GAPFILL_MARKERS = 23

#: The 19 checked-in transcript copies — the only transcript bytes this suite
#: may read. The engine's own project directory is off limits (P-M2-15).
TRANSCRIPT_COPIES_ROOT = PROBE_ROOT / "transcripts" / "copies"
EXPECTED_TRANSCRIPT_COPIES = 19

#: `_event` is the probe harness's label, not a hook event name: the settings
#: -file lane records the same payload under its own label
#: (`UserPromptSubmit__from_settings_json`, 6 captures). The payload's own
#: `hook_event_name` is the engine's word, so that is what `event` carries.
HARNESS_LABEL_SEPARATOR = "__"


@dataclass(frozen=True)
class CorpusEvent:
    """One captured envelope. `payload` is byte-equivalent to hook stdin."""

    event: str
    label: str
    epoch: float
    payload: Mapping[str, object]
    claude_pid: int
    scenario: str
    line: int
    source: str = ""
    """The capture file this envelope came from, **repo-relative** (T17).

    Carried rather than re-derived: corpus 1 and corpus 2 name their files
    differently and corpus 2 names two of them, so a fixture that reconstructed
    the path from `scenario` would be one rename away from citing a capture
    that does not exist. `test_composed_fixtures_name_their_captures` opens
    every one of these, which is what makes K1 mechanical.
    """

    @property
    def session_id(self) -> str:
        value = self.payload.get("session_id")
        return value if isinstance(value, str) else ""

    @property
    def raw(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    @property
    def received_at(self) -> str:
        return stamp(self.epoch)


def stamp(epoch: float) -> str:
    """A capture's `_epoch` as the receiver's stamp — UTC, second resolution."""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def scenario_files() -> list[Path]:
    return sorted(CORPUS_ROOT.glob("*/events.jsonl"))


def gapfill_files() -> list[Path]:
    """The second corpus's capture files, both spellings, de-duplicated.

    Sorted by path so the load order is the same on every machine, and
    de-duplicated because the two globs could overlap on a future scenario
    directory named `pidfd-pty-*` that also carried a `hooks.jsonl`.
    """
    found: set[Path] = set()
    for pattern in GAPFILL_HOOK_GLOBS:
        found.update(GAPFILL_ROOT.glob(pattern))
    return sorted(found)


def transcript_copies() -> list[Path]:
    """The 19 checked-in transcripts — the tails the stop fixtures pair with."""
    return sorted(TRANSCRIPT_COPIES_ROOT.rglob("*.jsonl"))


def load_corpus() -> list[CorpusEvent]:
    """Every captured envelope, merge-sorted on `_epoch` across session ids."""
    return _load(scenario_files())


def load_gapfill_corpus() -> list[CorpusEvent]:
    """The second corpus, in the same shape as the first (T17).

    The same `CorpusEvent`, so a stop fixture never has to know which corpus a
    capture came from — only the `scenario` and `line` it can be traced back
    to. The envelope differs in two ways and neither changes the payload: the
    harness's `MARKER` lines carry no `_epoch` (they sort first, at 0.0) and no
    `hook_event_name`, so `event` falls back to the `_event` label exactly as
    it already does for the settings-file lane in corpus 1.
    """
    return _load(gapfill_files())


def _load(paths: Sequence[Path]) -> list[CorpusEvent]:
    events: list[CorpusEvent] = []
    for path in paths:
        scenario = path.parent.name
        source = str(path.relative_to(REPO_ROOT))
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            envelope: object = json.loads(line)
            assert isinstance(envelope, dict), f"{scenario}:{index} is not an object"
            payload = envelope.get("payload")
            assert isinstance(payload, dict), f"{scenario}:{index} has no payload object"
            label = str(envelope.get("_event", ""))
            name = payload.get("hook_event_name")
            events.append(
                CorpusEvent(
                    event=str(name) if isinstance(name, str) and name else label,
                    label=label,
                    epoch=float(str(envelope.get("_epoch", 0.0))),
                    payload=payload,
                    claude_pid=int(str(envelope.get("_claude_pid", 0))),
                    scenario=scenario,
                    line=index,
                    source=source,
                )
            )
    events.sort(key=lambda item: (item.epoch, item.scenario, item.line))
    return events


def sequential_order(events: Sequence[CorpusEvent]) -> list[CorpusEvent]:
    """The sessions one after another, each in its own `_epoch` order."""
    grouped: dict[str, list[CorpusEvent]] = {}
    for event in events:
        grouped.setdefault(event.session_id, []).append(event)
    return [event for session in grouped.values() for event in session]


def corpus_digest() -> str:
    """One hash over every capture file — the corpora must be read-only (T12).

    Extended at T17 to the second corpus and the transcript copies, because
    those are now read too: a fixture that rewrote a capture to go green would
    otherwise be invisible to the guard that exists to catch exactly that.
    """
    digest = hashlib.sha256()
    for path in [*scenario_files(), *gapfill_files(), *transcript_copies()]:
        digest.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


# ----- the replay ----------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """What the replay's cwd → repo step returns. Deterministic and offline."""

    workspace_id: str
    repo_id: str | None
    repo_root: str
    """The **repo's** root, renamed from `root_path` when D57 dropped
    `workspace.root_path`: a project has no path, a repo does, and one name for
    two things is how the two get confused."""


Binder = Callable[[Store, str], Binding]


def offline_binder(store: Store, cwd: str) -> Binding:
    """cwd → workspace + repo without git.

    T7's real binder shells out to git against a directory that must exist; the
    probe's throwaway directories are long gone, so binding them live would test
    this host's filesystem rather than the fold. The mapping here is one repo per
    captured cwd, which is what those sessions actually had.
    """
    root = cwd or "/"
    workspace = store.create_project(name=Path(root).name or "local", description=None)
    repo = store.add_repo(
        workspace_id=workspace.id,
        root_path=root,
        name=Path(root).name or "local",
        git_common_dir=f"{root}/.git",
        vcs_remote=None,
    )
    return Binding(workspace_id=workspace.id, repo_id=repo.id, repo_root=root)


@dataclass
class ReplayStats:
    events: int = 0
    malformed: int = 0
    signals: int = 0
    registrations: int = 0
    min_active_subagents: int = 0
    anomalies: dict[str, int] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    repo_roots: dict[str, str] = field(default_factory=dict)
    briefs: dict[str, str] = field(default_factory=dict)


def replay(
    events: Iterable[CorpusEvent],
    store: Store,
    binder: Binder = offline_binder,
    drop: frozenset[str] = frozenset(),
) -> ReplayStats:
    """`payload` → `parse_hook_payload` → `fold` → `Store`, in the given order.

    The two cross-cutting rules the fold deliberately does not own are applied
    here, where they belong: **registration on the first event of any kind**
    (D47 — keyed on the absence of a row, never on a kind), and re-binding the
    repo when a session changes directory.

    `drop` suppresses whole `SignalKind` values by name, which is how C9 is
    tested: replay the corpus without the watch-path signals and see what, if
    anything, the agent's own edits lose.
    """
    stats = ReplayStats()
    priors: dict[str, SessionSnapshot] = {}
    for event in events:
        stats.events += 1
        signal = parse(event)
        if isinstance(signal, MalformedPayload):
            stats.malformed += 1
            continue
        stats.signals += 1
        if signal.kind.value in drop:
            continue

        engine_id = signal.engine_session_id
        prior = priors.get(engine_id)
        if prior is None:
            binding = binder(store, signal.cwd)
            session = store.register_session(
                engine_session_id=engine_id,
                workspace_id=binding.workspace_id,
                repo_id=binding.repo_id,
                cwd=signal.cwd,
                started_at=signal.received_at,
                origin=Origin.EXTERNAL,
                ownership=Ownership.ATTACHED,
            )
            stats.registrations += 1
            stats.sessions[engine_id] = session.id
            if binding.repo_id is not None:
                stats.repo_roots[binding.repo_id] = binding.repo_root
            found = store.snapshot(session.id)
            assert found is not None
            prior = found

        result = fold(signal, prior, signal.received_at)
        store.apply_fold_delta(prior.session_id, result.delta)
        prior = advance(prior, result)

        bound_root = None if prior.repo_id is None else stats.repo_roots.get(prior.repo_id)
        if result.delta.cwd is not None and result.delta.cwd != bound_root:
            rebound = binder(store, result.delta.cwd)
            if rebound.repo_id is not None and rebound.repo_id != prior.repo_id:
                store.apply_fold_delta(prior.session_id, FoldDelta(repo_id=rebound.repo_id))
                stats.repo_roots[rebound.repo_id] = rebound.repo_root
                prior = replace(prior, repo_id=rebound.repo_id)

        if prior.active_subagents < stats.min_active_subagents:
            stats.min_active_subagents = prior.active_subagents
        for anomaly in result.anomalies:
            store.bump_anomaly(anomaly.kind.value)
            stats.anomalies[anomaly.kind.value] = stats.anomalies.get(anomaly.kind.value, 0) + 1
        if prior.brief is not None:
            stats.briefs[engine_id] = prior.brief
        priors[engine_id] = prior
    return stats


def parse(event: CorpusEvent) -> Signal | MalformedPayload:
    """One capture through the adapter, stamped with its own receipt time."""
    return parse_hook_payload(event.raw, event.received_at)


def session_table(store: Store, stats: ReplayStats) -> dict[str, dict[str, object]]:
    """The per-session expected-state table, keyed on the ENGINE's session id.

    Never on `session.id`: that is a ulid minted from the wall clock, so it is
    the one value in the row that cannot be byte-identical run to run.
    """
    table: dict[str, dict[str, object]] = {}
    for engine_id, session_id in sorted(stats.sessions.items()):
        session = store.get_session(session_id)
        assert session is not None
        table[engine_id] = {
            "state": session.state.value,
            "cwd": session.cwd,
            "brief": session.brief,
            "model": session.model,
            "needs_you_reason": session.needs_you_reason,
            "tasks_total": session.tasks_total,
            "tasks_done": session.tasks_done,
            "active_subagents": session.active_subagents,
            "repos_touched": sorted(
                stats.repo_roots.get(repo_id, repo_id) for repo_id in session.repos_touched
            ),
            "started_at": session.started_at,
            "last_event_at": session.last_event_at,
            "ended_at": session.ended_at,
        }
    return table


# ----- the stops inside a corpus (T17) -------------------------------


@dataclass(frozen=True)
class StopOccurrence:
    """A stop as it happened: the adapter's signal, and the fold's prior."""

    event: CorpusEvent
    signal: Signal
    prior: SessionSnapshot

    @property
    def failure_error(self) -> str | None:
        value = self.signal.fields.get("failure_note")
        return value if isinstance(value, str) and value else None

    @property
    def end_reason(self) -> str | None:
        value = self.signal.fields.get("end_reason")
        return value if isinstance(value, str) and value else None

    @property
    def open_ledger(self) -> bool:
        return self.prior.tasks_total - self.prior.tasks_done > 0

    @property
    def key(self) -> str:
        return f"{self.event.scenario}/{self.event.line:04d}"


def blank_snapshot(engine_session_id: str) -> SessionSnapshot:
    """The prior a session starts from, with no store and no clock."""
    return SessionSnapshot(
        session_id=f"golden-{engine_session_id}",
        engine_session_id=engine_session_id,
        state=SessionState.RUNNING,
        last_event_at=None,
        observed_at=None,
        needs_you_reason=None,
        brief=None,
        cwd=None,
        repo_id=None,
        model=None,
        tasks_total=0,
        tasks_done=0,
        active_subagents=0,
        repos_touched=(),
        live_subagent_ids=frozenset(),
        created_task_ids=frozenset(),
        completed_task_ids=frozenset(),
        title=None,
        title_source="brief",
        pid=None,
        proc_start=None,
        ended_at=None,
        auto_compact_at=None,
        quota_notice_at=None,
    )


def stop_occurrences(events: Sequence[CorpusEvent]) -> list[StopOccurrence]:
    """Fold one corpus and stop at every signal a verdict is about.

    The prior handed to each occurrence is the state **before** the stop, which
    is what the live lane passes too: `HookLane` reads `Store.snapshot()` and
    then calls `handle_stop`.

    This loop carried `auto_compact_at` and `quota_notice_at` by hand until
    **BLOCKER T17-1 was fixed at its source**: `advance()` listed thirteen of
    `FoldDelta`'s fields and dropped seven, so the pure lane lost them after the
    first fold and `context_exhausted` had no fixture. `advance()` now reads the
    dataclass instead of a list (`tests/signals/test_advance_totality.py`), so
    the workaround is gone — a fixture that patches around a production defect
    keeps the suite green *and* keeps the defect, which is why it had to move
    rather than stay.
    """
    priors: dict[str, SessionSnapshot] = {}
    found: list[StopOccurrence] = []
    for event in events:
        signal = parse(event)
        if isinstance(signal, MalformedPayload):
            continue
        engine_id = signal.engine_session_id
        prior = priors.get(engine_id) or blank_snapshot(engine_id)
        if signal.kind in STOP_KINDS:
            found.append(StopOccurrence(event=event, signal=signal, prior=prior))
        priors[engine_id] = advance(prior, fold(signal, prior, signal.received_at))
    return found


def load_expected() -> dict[str, dict[str, object]]:
    decoded: object = json.loads(EXPECTED_TABLE.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    return {str(key): dict(value) for key, value in decoded.items() if isinstance(value, dict)}


def write_expected(table: Mapping[str, Mapping[str, object]]) -> None:
    """Only ever called behind `--update-golden` (T12): never automatically."""
    EXPECTED_TABLE.parent.mkdir(parents=True, exist_ok=True)
    EXPECTED_TABLE.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
