"""The hook lane's composition: frame → signal → fold → store → stream (T18).

ADR-1 caps `daemons/*` at 150 lines and forbids logic there, so this — the
sequence `controld` performs for every frame the ingest listener hands it — lives
in L3 where it can be tested without a process. `daemons/controld.py` constructs
one `HookLane` and calls `apply`.

It is the production twin of the golden lane's replay harness, which already
proves this exact shape over 429 real captured events (T12). The three rules the
pure fold deliberately does not own all live here, and each is here because it
is impure:

* **registration**, keyed on the absence of a row and never on a kind (D47) — a
  session that was already running when hooks were installed never announces
  itself again;
* **re-binding on a cwd change**, which runs git;
* **cross-repo attribution** (BLOCKER T11-3), which also runs git. `fold()`
  marks the session's *own* repo touched when a changed path is inside its cwd
  and leaves anything else alone, because identifying the other repo is exactly
  what a pure function cannot do. This is the composition root the blocker named
  as the only place the fix belongs.

The registry lane (`signals/discovery_loop.py`) is the other writer into the same
rows, returning the same `FoldResult`; both cross the one writer thread (D37).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from shepherd.core.fold_types import FoldDelta, SessionSnapshot
from shepherd.core.frames import Frame
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.signals import MalformedPayload, Signal
from shepherd.core.states import Origin, Ownership
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.normalise import parse_hook_payload
from shepherd.signals.binding import bind_cwd_to_repo
from shepherd.signals.fold import fold
from shepherd.logs.stops import StopLog
from shepherd.signals.fields import read_changed_paths
from shepherd.signals.stop_lane import STOP_KINDS, handle_stop
from shepherd.store.db import Store

__all__ = ["HookLane", "MALFORMED_ANOMALY"]

#: §8: an unreadable payload is counted under one key, never raised into a hook.
MALFORMED_ANOMALY = AnomalyKind.MALFORMED_PAYLOAD.value

Publisher = Callable[[StreamEvent], int]

#: `(session_id, new_engine_session_id)` — C14's move, performed by whoever owns
#: the store verbs. The lane is handed the callback; it does not contain the move.
Rebound = Callable[[str, str], None]

#: `(session_id,)` — T14's delivery trigger at a turn boundary.
StopDeliver = Callable[[str], None]


class HookLane:
    """One store, one publisher, one frame at a time.

    Called from the ingest listener's thread. Every write goes through `Store`,
    which owns the single writer thread, so this class holds no lock of its own
    and no state between frames — the prior it folds against is read back out of
    the database, which is what makes a `controld` restart lose nothing (D37).
    """

    def __init__(
        self,
        store: Store,
        publish: Publisher,
        stop_log: StopLog | None = None,
        projects_root: Path | None = None,
        on_engine_session_rebound: Rebound | None = None,
        on_stop_deliver: StopDeliver | None = None,
    ) -> None:
        self._store = store
        self._publish = publish
        #: **Defaulted**, so every M1 call site keeps working (T18-3). Both
        #: arrive from the composition root, which is the only place allowed
        #: to resolve a directory; without them the lane is exactly M1's and
        #: no stop is ever classified.
        self._stop_log = stop_log
        self._projects_root = projects_root
        #: M3's two, defaulted for the same reason and landing **here and
        #: nowhere else**. `on_engine_session_rebound` is deliberately not
        #: spelled `rebind`: `_rebind` below already means something else in
        #: this module (it re-binds a moved session to a *repo*), and two
        #: `rebind`s in one file is the hazard M2 recorded for `replay`. Both
        #: are added by one task because this plan's hard rule is that no two
        #: tracks share a file — half of M1's blocker file is two builders in
        #: one module. T12 wires the first to `orchestration.lifecycle.rebind`
        #: (C14); T14 consumes the second and does not open this file.
        #:
        #: **Neither is invoked from `apply` yet, deliberately.** The trigger for
        #: the first is `SessionEnd{reason:resume}` followed by
        #: `SessionStart{source:resume}` in one pane, and that pairing has **no
        #: captured example**: `data-schemas.md` records `resume` as a binary-enum
        #: value with the TUI `/resume` switch never attempted. K1 forbids
        #: asserting a shape no capture shows, so the seam is opened and the
        #: detector is not invented. The second is T14's to call.
        self._on_engine_session_rebound = on_engine_session_rebound
        self._on_stop_deliver = on_stop_deliver

    def apply(self, frame: Frame) -> None:
        """Fold one frame into the store and publish what it changed."""
        parsed = parse_hook_payload(frame.payload, frame.received_at)
        if isinstance(parsed, MalformedPayload):
            self._store.bump_anomaly(MALFORMED_ANOMALY)
            return
        session_id = self._session_id_for(parsed)
        prior = self._store.snapshot(session_id)
        result = fold(parsed, prior, frame.received_at)
        delta = self._with_foreign_repos(parsed, prior, result.delta)
        self._store.apply_fold_delta(session_id, delta)
        if delta.cwd is not None:
            self._rebind(session_id, delta.cwd, prior)
        for anomaly in result.anomalies:
            self._store.bump_anomaly(anomaly.kind.value)
        for event in result.events:
            self._publish(
                StreamEvent(
                    kind=event.kind,
                    session_id=session_id,
                    payload=event.payload,
                    occurred_at=event.occurred_at,
                )
            )
        self._classify(parsed, prior, frame.received_at)

    def _classify(
        self, signal: Signal, prior: SessionSnapshot | None, received_at: str
    ) -> None:
        """T11's one call site. The prior is the **pre-fold** snapshot, which
        is what carries the two marks: the fold clears the compaction one on a
        turn ending, and reading it afterwards would read the clear.

        The lane calls `handle_stop`; it does not contain it (ADR-M2-7), and it
        constructs neither collaborator — both were handed to it.
        """
        if signal.kind not in STOP_KINDS or prior is None:
            return
        if self._stop_log is None or self._projects_root is None:
            return
        handle_stop(
            signal=signal,
            prior=prior,
            projects_root=self._projects_root,
            received_at=received_at,
            store=self._store,
            stop_log=self._stop_log,
            publish=self._publish,
        )

    # ----- the three impure rules -------------------------------------------

    def _session_id_for(self, signal: Signal) -> str:
        """D47: the first event of *any* kind registers the session."""
        existing = self._store.get_session_by_engine_id(signal.engine_session_id)
        if existing is not None:
            return existing.id
        binding = bind_cwd_to_repo(self._store, signal.cwd)
        registered = self._store.register_session(
            engine_session_id=signal.engine_session_id,
            workspace_id=binding.workspace_id,
            repo_id=binding.repo_id,
            cwd=signal.cwd,
            started_at=signal.received_at,
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        return registered.id

    def _rebind(self, session_id: str, cwd: str, prior: SessionSnapshot | None) -> None:
        """A session that moved may have moved into a different repo (runs git)."""
        binding = bind_cwd_to_repo(self._store, cwd)
        current = None if prior is None else prior.repo_id
        if binding.repo_id is not None and binding.repo_id != current:
            self._store.apply_fold_delta(session_id, FoldDelta(repo_id=binding.repo_id))

    def _with_foreign_repos(
        self, signal: Signal, prior: SessionSnapshot | None, delta: FoldDelta
    ) -> FoldDelta:
        """BLOCKER T11-3: attribute a changed path that is outside the cwd.

        The fold has already merged the session's own repo for any path inside
        its cwd; what is left are the paths it could not name. Each is resolved
        through the same `bind_cwd_to_repo` the registration uses — one git call
        per *directory*, and only for a path the fold left unattributed. A path
        that resolves to no repo stays unattributed rather than guessed at.
        """
        outside = self._paths_outside(signal, prior)
        if not outside:
            return delta
        known = set(delta.repos_touched if delta.repos_touched is not None else ())
        if prior is not None:
            known |= set(prior.repos_touched)
        found = set(known)
        for directory in sorted({str(Path(path).parent) for path in outside}):
            binding = bind_cwd_to_repo(self._store, directory)
            if binding.repo_id is not None:
                found.add(binding.repo_id)
        if found == known:
            return delta
        return replace(delta, repos_touched=tuple(sorted(found)))

    @staticmethod
    def _paths_outside(signal: Signal, prior: SessionSnapshot | None) -> tuple[str, ...]:
        """The changed paths the pure fold could not attribute (C9's remainder)."""
        cwd = signal.cwd or (None if prior is None else prior.cwd)
        if not cwd:
            return ()
        root = cwd.rstrip("/")
        return tuple(
            path
            for path in read_changed_paths(signal)
            if path != root and not path.startswith(f"{root}/")
        )
