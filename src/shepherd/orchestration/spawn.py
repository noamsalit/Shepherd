"""T11 — the spawn sequence: the row before the process, the poll, the dialog.

Steps 3 to 8, with `Store`, `Runner`, `now`, a publisher, the server-ensure and
the poll's `sleep` injected. Steps 1 and 2 — §13's registered roots, D-5 and
§11's three caps — are `admission.admit()`, a sibling module: the plan's ≤ 300
line artifact and two different jobs both said so. Nothing here opens a
connection, reads a clock, starts a process or spells a multiplexer word.

**The row exists before the process does (C-M3-7).** `create_owned_session` is
step 4 and `runner.start` is step 5, so a spawn that dies between them leaves a
handle-less row for T12's reconcile — never a live `claude` with no row.

**A spawn answers no dialog, ever (clause 3, C-M3-5).** This module calls
`start` and `pane` and no other member, so it sends no key by construction. A
bare `Enter` on the trust screen selects **"No, exit"** (A11) and the session
exits 1; an untrusted directory becomes `needs_you` with the directory named
(N13) and a human answers it.

**Three recorded deviations from the plan's `Produces`.** `ensure_server`,
`sleep` and `engine_config_home` are **required** injections — `ensure_server` is
not one of the `Runner` seam's ten members and the seam is held by another task,
`sleep` keeps the poll deterministic without a second clock, and
`engine_config_home` has been required at every call site since T10-R2 (its old
default was the user's real `~/.claude.json`). And `resolve_binary` is **not**
called here: the composition root binds the binary into the injected `spawn_argv`
(T8-1/T23), which is where E-M3-14's "resolved before the spawn" already happens;
a second `PATH` probe here would answer a question this module cannot use.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import parse_stamp
from shepherd.core.fold_types import FoldDelta
from shepherd.core.ids import new_ulid
from shepherd.core.runner import (
    SPAWN_POLL_INTERVAL_S,
    SPAWN_TIMEOUT_S,
    PaneKind,
    PaneState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
)
from shepherd.core.states import Origin, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.trust import TrustState, trust_state
from shepherd.orchestration.admission import CAP_CHILDREN, CAP_DEPTH, CAP_TOTAL, admit
from shepherd.runner.base import Runner
from shepherd.store.db import Store

#: Re-exported because `SpawnRefused` is what a caller of *this* module catches:
#: `spawn_owned_session` is the published entry point and its refusal type must
#: be importable beside it. An alias, never a second class — two structurally
#: identical types are the split `mypy` only catches where they happen to meet.
from shepherd.orchestration.admission import SpawnRefused as SpawnRefused

__all__ = [
    "CAP_CHILDREN",
    "CAP_DEPTH",
    "CAP_TOTAL",
    "POLL_OUTCOME",
    "SPAWN_EVENT",
    "SpawnOutcome",
    "SpawnRefused",
    "spawn_owned_session",
]

SPAWN_EVENT = "session.spawned"

#: What the poll does with each of the six pane kinds. **Total over `PaneKind`**,
#: asserted as a set equality against the enum and never as a length: a missing
#: row is a fourth outcome escaping unlabelled. `None` decides nothing yet.
POLL_OUTCOME: dict[PaneKind, SessionState | None] = {
    PaneKind.PROMPT_READY: SessionState.STARTING,
    PaneKind.TRUST_DIALOG: SessionState.NEEDS_YOU,
    PaneKind.DEAD: SessionState.STOPPED,
    PaneKind.PERMISSION_DIALOG: None,
    PaneKind.BUSY: None,
    PaneKind.UNREADABLE: None,
}

#: The poll's second bound. The deadline is arithmetic over the injected `now`;
#: this is what keeps the loop finite if a clock ever stalls.
MAX_POLLS = int(SPAWN_TIMEOUT_S / SPAWN_POLL_INTERVAL_S)

#: `SessionSpec.runner` before step 5. Which driver this is, is the composition
#: root's fact and the **handle** is where it arrives; a name guessed here is a
#: value on the request that the row then contradicts (principle 5).
UNKNOWN_RUNNER = "unknown"


@dataclass(frozen=True)
class SpawnOutcome:
    """A spawn that happened. `state` is the row's state when the poll resolved."""

    session_id: str
    state: SessionState
    detail: str


@dataclass(frozen=True)
class _Resolution:
    """What the poll resolved to. `kind` is `None` only for the fourth outcome —
    the window closed with nothing decisive — which the caller **counts**."""

    state: SessionState
    detail: str
    exit_code: int | None
    kind: PaneKind | None


def _poll(
    runner: Runner, handle: RunnerHandle, now: Callable[[], str], sleep: Callable[[float], None]
) -> PaneState | None:
    """Step 6: read the pane until it decides, or until §8's timeout.

    `None` is the fourth outcome — nothing decisive inside the window — which the
    caller labels and counts. A pane the driver refuses to read is polled through
    rather than raised on: that refusal is normal while a pane is coming up.
    """
    started = parse_stamp(now())
    for _ in range(MAX_POLLS):
        observed: PaneState | None
        try:
            observed = runner.pane(handle)
        except RunnerRefusal:
            observed = None
        if observed is not None and POLL_OUTCOME[observed.kind] is not None:
            return observed
        sleep(SPAWN_POLL_INTERVAL_S)
        moment = parse_stamp(now())
        if started is not None and moment is not None:
            if (moment - started).total_seconds() >= SPAWN_TIMEOUT_S:
                return None
    return None


def _resolution(pane: PaneState | None, cwd: str) -> _Resolution:
    """Step 7: the three decisive outcomes, and the counted fourth."""
    if pane is None:
        return _Resolution(
            SessionState.NEEDS_YOU, f"pane state unreadable after {int(SPAWN_TIMEOUT_S)}s",
            None, None,
        )
    decided = POLL_OUTCOME[pane.kind]
    if decided is SessionState.NEEDS_YOU:
        return _Resolution(decided, f"workspace trust: {cwd}", None, pane.kind)
    if decided is SessionState.STOPPED:
        status = pane.fields.pane_dead_status
        return _Resolution(decided, f"the pane exited with status {status}", status, pane.kind)
    assert decided is SessionState.STARTING  # POLL_OUTCOME is total; this is the third row
    return _Resolution(
        # The engine's own hook name stays in its adapter (§5.0): this layer says
        # what happens, not which event carries it.
        decided, "the prompt is ready; the hook lane moves the row on from here",
        None, pane.kind,
    )


def _record(
    store: Store, session_id: str, found: _Resolution, now: Callable[[], str]
) -> None:
    """The row's side of step 7, and the unknown's count.

    A `stopped` row gets the state and nothing more: the exit code reaches it
    through T12's `observe_exit`, and the stop **verdict** has exactly one writer
    (`apply_stop_verdict`, M2's lane). A spawn decides neither.
    """
    if found.state is SessionState.NEEDS_YOU:
        store.apply_fold_delta(
            session_id,
            FoldDelta(state=found.state, needs_you_reason=found.detail, last_event_at=now()),
        )
    elif found.state is SessionState.STOPPED:
        store.apply_fold_delta(session_id, FoldDelta(state=found.state, last_event_at=now()))
    if found.kind is None:
        store.bump_anomaly(AnomalyKind.PANE_UNREADABLE.value)


def spawn_owned_session(
    *,
    store: Store,
    runner: Runner,
    now: Callable[[], str],
    sleep: Callable[[float], None],
    publish: Callable[[StreamEvent], None],
    ensure_server: Callable[[], None],
    engine_config_home: Path | None,
    workspace_id: str,
    cwd: str,
    brief: str | None,
    title: str | None,
    model: str | None,
    effort: str | None,
    parent_session_id: str | None,
    origin: Origin,
    ephemeral: bool = False,
) -> SpawnOutcome | SpawnRefused:
    """Start one owned session. Every failure is a `SpawnRefused`, never a raise."""
    admitted = admit(
        store=store,
        runner=runner,
        workspace_id=workspace_id,
        cwd=cwd,
        parent_session_id=parent_session_id,
    )
    if isinstance(admitted, SpawnRefused):
        return admitted
    here = str(admitted.cwd)

    # Step 3, before anything is started: a directory the engine has no accepted
    # trust dialog for will stop on one, and that is worth knowing in advance.
    trust: TrustState = trust_state(here, engine_config_home)

    session_id, engine_session_id = new_ulid(), str(uuid.uuid4())
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=engine_session_id,
        workspace_id=workspace_id,
        repo_id=None,
        cwd=here,
        started_at=now(),
        origin=origin,
        parent_session_id=parent_session_id,
        depth=admitted.depth,
        ephemeral=ephemeral,
        title=title,
        title_source="user" if title is not None else "brief",
        handle=None,
        model=model,
        effort=effort,
    )

    spec = SessionSpec(
        session_id=session_id,
        engine_session_id=engine_session_id,
        cwd=here,
        brief=brief,
        title=title,
        model=model,
        effort=effort,
        engine="claude_code",
        runner=UNKNOWN_RUNNER,
        env={},
    )
    try:
        ensure_server()
        handle = runner.start(spec)
    except RunnerRefusal as refusal:
        return SpawnRefused(refusal.reason, None)
    store.set_runner_handle(session_id, handle)

    found = _resolution(_poll(runner, handle, now, sleep), here)
    _record(store, session_id, found, now)
    publish(
        StreamEvent(
            kind=SPAWN_EVENT,
            session_id=session_id,
            occurred_at=now(),
            payload={
                "cwd": here,
                "engine_session_id": engine_session_id,
                "state": found.state.value,
                "detail": found.detail,
                "exit_code": found.exit_code,
                # `unreadable` when the window closed with nothing decisive: a
                # value, never a blank (principle 5).
                "pane_kind": (found.kind or PaneKind.UNREADABLE).value,
                "trusted": trust.trusted,
                "trust_source": trust.source,
            },
        )
    )
    return SpawnOutcome(session_id=session_id, state=found.state, detail=found.detail)
