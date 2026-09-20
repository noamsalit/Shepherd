"""Hookless discovery: the registry scan, the liveness sweep, and the cadence.

This module is the second writer-lane into the same `session` row the hook path
writes (D37, D47): it turns one live-session sidecar into the **same**
`FoldDelta` the fold produces, so there is one writer and one rule set. It
exists because the user's machine has no hooks installed, and without it the
fleet page is empty on the only machine that exists (Decision pressure 5).

Three rules are load-bearing here and each is a captured observation, not a
preference:

* **`idle` is never `stopped`.** §8 defines `stopped` as a stop signal or an
  *observed process exit*; an idle live process is neither, and the capture
  `04-sidecar-idle.json` shows `status` stayed `idle` right across the 60 s
  idle notification. Idle splits on the age of `statusUpdatedAt`, exactly as §8
  splits (Decision pressure 6).
* **The only stop this lane may assert is an observed process exit**, via
  `HostPlatform.process_liveness(pid, proc_start)`. A vanished sidecar is not a
  stop (E29/P16) — the file is deleted on exit *and* absent before the trust
  dialog is accepted, so absence cannot tell the two apart.
* **Recency decides, not source** (RD8). Each observation carries
  `observed_at`; an older one never overwrites a newer one, and the hook path
  wins only the exact tie.

`run_discovery_loop` owns the 2.0 s cadence, the sweep and the shutdown join
because ADR-1 caps `daemons/*` at 150 lines and forbids logic there.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.clock import parse_stamp, stamp, utc_now
from shepherd.core.fold_types import CLEARED, FoldDelta, FoldResult, SessionSnapshot
from shepherd.core.mailbox import MailboxCounts
from shepherd.core.states import (
    TITLE_SOURCE_RANK,
    Origin,
    Ownership,
    SessionState,
    TitleSource,
)
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.hooks_config import inspect_hooks
from shepherd.engines.claude_code.registry import (
    BLOCKED_REASON,
    DERIVED_NAME_SOURCE,
    IDLE_REASON,
    SDK_CLI_ENTRYPOINT,
    USER_NAME_SOURCE,
    RegistryEntry,
    claude_config_dir,
    is_attached_interactive,
    scan_registry,
)
from shepherd.host.base import HostPlatform, Liveness
from shepherd.signals.binding import bind_cwd_to_repo
from shepherd.store.db import Store

#: Sidecar files only — never `claude agents --json`, which forks a process per
#: call (E33, G11). This module is the single module that names it.
REGISTRY_SCAN_INTERVAL_S = 2.0

#: §8's idle threshold, measured at 60.03 s from the captured notification (C21).
IDLE_TO_NEEDS_YOU_S = 60.0

#: The three *observed* `status` values. The set is open, not closed: shapes were
#: verified at engine 2.1.270 while this host runs 2.1.273 (G12), so anything
#: else keeps the prior state and is counted (principle 5).
BUSY_STATUS = "busy"
IDLE_STATUS = "idle"
WAITING_STATUS = "waiting"

#: Both lanes clear a reason with the one `core/` constant (BLOCKER T7b-4,
#: T11-6): agreeing by coincidence is not agreeing by construction.
CLEARED_REASON = CLEARED

DISCOVERY_STATUS_KEY = "discovery_status"
SETTINGS_FILENAME = "settings.json"
HOOKS_INSTALLED = "installed"
HOOKS_ABSENT = "absent"

STATE_EVENT_KIND = "session.state"
REGISTRY_SOURCE = "registry"

#: D29's ratchet: a user-chosen name outranks an engine-derived one, and an
#: engine-derived one never overwrites it. The rank itself is `core/`'s
#: (`TITLE_SOURCE_RANK`); this map is the engine's spelling of it.
_NAME_SOURCE_TO_TITLE_SOURCE: dict[str, TitleSource] = {
    USER_NAME_SOURCE: "user",
    DERIVED_NAME_SOURCE: "engine",
}


@dataclass(frozen=True)
class DiscoveryStatus:
    """What `doctor` (T17) and `fleet_summary` (T14) report, without importing
    this module's constants: it is published to `app_state` each pass."""

    hooks: str
    registry_sessions: int
    sdk_cli_skipped: int
    sdk_cli_reconciled: int
    """T19-1/DP2: `sdk-cli` rows this pass moved to `ephemeral` (§7's own word
    for "real, and not on the board by default"). Counts *changes*, not matches:
    a row already `ephemeral` — an `ask()` fork, which is `ephemeral` from birth
    — is not counted again on the next sweep."""

    sdk_cli_missed: int
    """The half that stops `sdk_cli_reconciled` reading as coverage.

    A `-p` run shorter than one 2.0 s sweep has had its sidecar **deleted at
    exit** before any scan saw it (`registry.py`), so the reconcile can never
    reach the row the hook lane left behind. This counts the rows in that
    position: registered by the hook lane, still on the fleet page, and never
    once observed by this lane — `pid IS NULL`, which is only a truthful reading
    of "no sweep has seen it" because **this module is the sole writer of that
    column** (`test_only_the_registry_lane_writes_pid`).

    It is an **upper bound**, named rather than discovered, in T12-2's shape: a
    row the registry never saw could equally be an interactive session that
    ended before Shepherd first ran. Nothing observed which, and principle 5's
    answer to that is to count it and say so — not to leave it out of the line.
    It is a standing backlog, not a per-pass rate: it falls the moment a sweep
    observes the row, and `test_missed_stops_counting_a_row_the_sweep_does_see`
    is its negative control."""

    skipped_other: int
    unknown_status: int
    scan_interval_s: float
    last_scan_at: str


def iso_from_epoch_ms(epoch_ms: int) -> str:
    """Epoch milliseconds (the sidecar's stamp format) → ISO-8601 UTC, ms precision."""
    return stamp(datetime.fromtimestamp(epoch_ms / 1000, UTC))


def _seconds(text: str) -> float:
    """RD8's recency comparison, numeric and never lexical: `…:56Z` sorts *after*
    `…:56.789Z` as text, which would invert it.

    An unreadable stamp is the beginning of time rather than an exception: this
    runs inside the scan loop, and a row whose stamp we cannot read must lose a
    recency tie to one we can, not stop the pass (principle 5).
    """
    moment = parse_stamp(text)
    return 0.0 if moment is None else moment.timestamp()


def liveness_verdict(entry: RegistryEntry, liveness: Liveness) -> bool:
    """Is the process behind this entry the same live process? (E31)

    A different `procStart` is a **different** process that happens to hold the
    pid, so it is not alive for our purposes.
    """
    if not liveness.alive:
        return False
    if not entry.proc_start or liveness.start_token is None:
        return True
    return liveness.start_token == entry.proc_start


def title_from_registry(
    entry: RegistryEntry, prior: SessionSnapshot | None
) -> tuple[str, TitleSource] | None:
    """D29's ratchet applied to `name`/`nameSource`, or `None` to leave it alone.

    An unrecognised `nameSource` is not a rank we can hold, so it is declined
    rather than guessed — the same treatment an unrecognised `status` gets.
    """
    if entry.name is None or entry.name_source is None:
        return None
    title_source = _NAME_SOURCE_TO_TITLE_SOURCE.get(entry.name_source)
    if title_source is None:
        return None
    if prior is not None and prior.title is not None:
        if TITLE_SOURCE_RANK[prior.title_source] > TITLE_SOURCE_RANK[title_source]:
            return None
    return entry.name, title_source


def _title_pair(
    entry: RegistryEntry, prior: SessionSnapshot | None
) -> tuple[str | None, TitleSource | None]:
    """The ratchet's output as two delta fields, `(None, None)` when it declines.

    `title` and `title_source` are written together or not at all: a source
    with no title is a rank held over nothing (BLOCKER T7b-3).
    """
    decided = title_from_registry(entry, prior)
    return (None, None) if decided is None else decided


def _state_event(state: SessionState, session_id: str | None, occurred_at: str) -> StreamEvent:
    return StreamEvent(
        kind=STATE_EVENT_KIND,
        session_id=session_id,
        payload={"state": str(state.value), "source": REGISTRY_SOURCE},
        occurred_at=occurred_at,
    )


def registry_delta(
    entry: RegistryEntry,
    liveness: Liveness,
    prior: SessionSnapshot | None,
    now: str,
) -> FoldResult:
    """Pure: one sidecar plus one liveness reading → the same shape `fold()` returns.

    No clock and no I/O: `now` is a parameter, which is what makes the six rows
    of Decision pressure 6's table a deterministic test.
    """
    observed_at = iso_from_epoch_ms(entry.status_updated_at_ms)
    session_id = prior.session_id if prior is not None else None

    # RD8: recency decides. An equal stamp ties to the hook path, which is precise.
    if (
        prior is not None
        and prior.observed_at is not None
        and _seconds(prior.observed_at) >= _seconds(observed_at)
    ):
        return FoldResult(delta=FoldDelta(), events=(), anomalies=())

    # D29's ratchet, decided once against the prior and carried by every branch:
    # a title is a fact about the session, not about the state it is in.
    title, title_source = _title_pair(entry, prior)

    if not liveness_verdict(entry, liveness):
        # §8's fourth stop trigger, verbatim: "observed process exit".
        delta = FoldDelta(
            state=SessionState.STOPPED,
            ended_at=liveness.observed_at,
            observed_at=observed_at,
            last_event_at=observed_at,
            title=title,
            title_source=title_source,
            pid=entry.pid,
            proc_start=entry.proc_start or None,
        )
        return FoldResult(
            delta=delta,
            events=(_state_event(SessionState.STOPPED, session_id, liveness.observed_at),),
            anomalies=(),
        )

    state, reason, anomalies = _state_for(entry, observed_at, now)
    if state is None:
        # Unknown status: keep the prior state, count it, never guess (A9).
        delta = FoldDelta(
            cwd=entry.cwd,
            observed_at=observed_at,
            title=title,
            title_source=title_source,
            pid=entry.pid,
            proc_start=entry.proc_start or None,
        )
        return FoldResult(delta=delta, events=(), anomalies=anomalies)

    if reason is None and prior is not None and prior.needs_you_reason:
        # Leaving `waiting` is the only observed signal that a permission prompt
        # was resolved (the capture pair 06 → 07, 9.194 s apart).
        reason = CLEARED_REASON

    delta = FoldDelta(
        state=state,
        needs_you_reason=reason,
        cwd=entry.cwd,
        last_event_at=observed_at,
        observed_at=observed_at,
        title=title,
        title_source=title_source,
        pid=entry.pid,
        proc_start=entry.proc_start or None,
    )
    return FoldResult(
        delta=delta,
        events=(_state_event(state, session_id, observed_at),),
        anomalies=anomalies,
    )


def _state_for(
    entry: RegistryEntry, observed_at: str, now: str
) -> tuple[SessionState | None, str | None, tuple[Anomaly, ...]]:
    """Decision pressure 6's table, one row per branch, for a **live** process."""
    if entry.status == BUSY_STATUS:
        return SessionState.RUNNING, None, ()
    if entry.status == IDLE_STATUS:
        if _seconds(now) - _seconds(observed_at) < IDLE_TO_NEEDS_YOU_S:
            return SessionState.RUNNING, None, ()
        return SessionState.NEEDS_YOU, IDLE_REASON, ()
    if entry.status == WAITING_STATUS:
        return SessionState.NEEDS_YOU, entry.waiting_for or BLOCKED_REASON, ()
    anomaly = Anomaly(
        kind=AnomalyKind.UNKNOWN_REGISTRY_STATUS,
        detail=f"unrecognised registry status {entry.status!r} at engine {entry.version}",
        engine_session_id=entry.session_id,
    )
    return None, None, (anomaly,)


def liveness_sweep(store: Store, host: HostPlatform, now: str) -> tuple[FoldResult, ...]:
    """End every session whose process is observed gone (DP7, P17).

    The inputs are the stored `pid`/`proc_start` columns rather than anything in
    memory, so the sweep still works after a `controld` restart — and after the
    sidecar that supplied them has been deleted.
    """
    results: list[FoldResult] = []
    for session_id, pid, proc_start in store.sessions_with_liveness_inputs():
        liveness = host.process_liveness(pid, proc_start)
        if liveness.alive and (
            liveness.start_token is None or liveness.start_token == proc_start
        ):
            continue
        delta = FoldDelta(
            state=SessionState.STOPPED,
            ended_at=liveness.observed_at,
            observed_at=liveness.observed_at,
        )
        store.apply_fold_delta(session_id, delta)
        results.append(
            FoldResult(
                delta=delta,
                events=(
                    _state_event(SessionState.STOPPED, session_id, liveness.observed_at),
                ),
                anomalies=(),
            )
        )
    return tuple(results)


def reconcile_sdk_cli(store: Store, engine_session_id: str) -> bool:
    """DP2 option 2: hide the row a hooked `claude -p` run left on the fleet page.

    **Registration is unchanged.** D47 still accepts the first event of any kind,
    because the hook lane cannot apply E35's discriminator — `entrypoint` is
    absent from all 429 captured hook payloads and exists only in this sidecar.
    So the row is created, and this lane corrects it on the next sweep.

    The row is **not deleted**: a `-p` run genuinely happened, and `ephemeral` is
    §7's word for a real session that is off the board by default. `True` only
    when this call *changed* something, so a steady state stops counting.
    """
    session = store.get_session_by_engine_id(engine_session_id)
    if session is None or session.ephemeral:
        return False
    store.set_ephemeral(session.id, True)
    return True


def missed_sdk_cli(store: Store) -> int:
    """Rows no sweep has ever seen — the counter that refuses to claim coverage.

    `ownership` is the first filter: a session Shepherd **owns** was pre-
    registered by Shepherd (DP2 half one), so its absence from the registry says
    nothing about a `-p` run. What is left is the hook lane's own population,
    and `pid IS NULL` is the observable difference between "the registry has
    seen this row" and "it never will".
    """
    return sum(
        1
        for row in store.list_sessions()
        if not row.ephemeral
        and row.ownership is Ownership.ATTACHED
        and row.origin is Origin.EXTERNAL
        and row.pid is None
    )


def discovery_pass(
    store: Store,
    host: HostPlatform,
    on_result: Callable[[FoldResult], None],
    now: str,
    engine_config_dir: Path | None = None,
) -> DiscoveryStatus:
    """One scan: register what is new, apply what changed, count what is unknown.

    `engine_config_dir` defaults to the **engine's** config dir — never
    `host.dirs().config_dir`, which is Shepherd's own (ADR-2). It is a parameter
    so a test can point the scan at a throwaway directory instead of the user's.
    """
    config_dir = engine_config_dir if engine_config_dir is not None else claude_config_dir()
    entries, anomalies = scan_registry(config_dir)
    for anomaly in anomalies:
        store.bump_anomaly(anomaly.kind.value)

    registry_sessions = 0
    sdk_cli_skipped = 0
    sdk_cli_reconciled = 0
    skipped_other = 0
    unknown_status = 0

    for entry in entries:
        if not is_attached_interactive(entry):
            # `entrypoint` is the discriminator; `kind` is `interactive` for a
            # `-p` run too, so branching on it would flicker every `-p` run
            # through the fleet page (E35, probe Finding 1).
            if entry.entrypoint == SDK_CLI_ENTRYPOINT:
                sdk_cli_skipped += 1
                sdk_cli_reconciled += int(reconcile_sdk_cli(store, entry.session_id))
            else:
                skipped_other += 1
            continue

        registry_sessions += 1
        session = store.get_session_by_engine_id(entry.session_id)
        if session is None:
            binding = bind_cwd_to_repo(store, entry.cwd)
            session = store.register_session(
                engine_session_id=entry.session_id,
                workspace_id=binding.workspace_id,
                repo_id=binding.repo_id,
                cwd=entry.cwd,
                started_at=iso_from_epoch_ms(entry.started_at_ms),
                origin=Origin.EXTERNAL,
                ownership=Ownership.ATTACHED,
            )

        liveness = host.process_liveness(entry.pid, entry.proc_start)
        result = registry_delta(entry, liveness, store.snapshot(session.id), now)
        for anomaly in result.anomalies:
            store.bump_anomaly(anomaly.kind.value)
            if anomaly.kind is AnomalyKind.UNKNOWN_REGISTRY_STATUS:
                unknown_status += 1
        if _writes_anything(result.delta):
            store.apply_fold_delta(session.id, result.delta)
        on_result(
            replace(
                result,
                events=tuple(
                    replace(event, session_id=session.id) for event in result.events
                ),
            )
        )

    status = DiscoveryStatus(
        hooks=_hooks_state(config_dir / SETTINGS_FILENAME),
        registry_sessions=registry_sessions,
        sdk_cli_skipped=sdk_cli_skipped,
        sdk_cli_reconciled=sdk_cli_reconciled,
        sdk_cli_missed=missed_sdk_cli(store),
        skipped_other=skipped_other,
        unknown_status=unknown_status,
        scan_interval_s=REGISTRY_SCAN_INTERVAL_S,
        last_scan_at=now,
    )
    store.set_app_state(DISCOVERY_STATUS_KEY, _as_mapping(status))
    return status


def run_discovery_loop(
    store: Store,
    host: HostPlatform,
    on_result: Callable[[FoldResult], None],
    shutdown: threading.Event,
    engine_config_dir: Path | None = None,
    sweep: Callable[[], MailboxCounts] | None = None,
) -> None:
    """Own the cadence, both sweeps and the shutdown (ADR-1: `daemons/` may not).

    The wait is on the event rather than on a sleep, so shutdown is observed
    immediately instead of after up to one full interval.

    `sweep` is T14's mailbox pass (T23), and it rides **this** cadence rather
    than a fourth thread: D45's second delivery trigger is "the pane is
    prompt-ready", which is the same 2.0 s observation this loop already makes,
    and `sessions_with_pending()` is one indexed query, so an empty mailbox costs
    nothing. `None` means a composition that wired no mailbox — an answer, not an
    absence: `daemons/` may not decide it, so it arrives as a value.
    """
    while not shutdown.is_set():
        now = _now()
        discovery_pass(store, host, on_result, now, engine_config_dir)
        for result in liveness_sweep(store, host, now):
            on_result(result)
        if sweep is not None:
            sweep()
        if shutdown.wait(REGISTRY_SCAN_INTERVAL_S):
            return


def _now() -> str:
    return utc_now()


def _writes_anything(delta: FoldDelta) -> bool:
    return any(
        getattr(delta, name) is not None
        for name in FoldDelta.__dataclass_fields__
        if name != "observed_at"
    )


def _hooks_state(settings_path: Path) -> str:
    """Read-only: whether our managed hook entries are in the settings file.

    This is the `doctor` line's `hooks:` half. It never writes, and the hook
    path is the richer source that switches on when the user installs them.
    """
    return HOOKS_INSTALLED if inspect_hooks(settings_path).installed else HOOKS_ABSENT


def _as_mapping(status: DiscoveryStatus) -> dict[str, object]:
    return {
        "hooks": status.hooks,
        "registry_sessions": status.registry_sessions,
        "sdk_cli_skipped": status.sdk_cli_skipped,
        "sdk_cli_reconciled": status.sdk_cli_reconciled,
        "sdk_cli_missed": status.sdk_cli_missed,
        "skipped_other": status.skipped_other,
        "unknown_status": status.unknown_status,
        "scan_interval_s": status.scan_interval_s,
        "last_scan_at": status.last_scan_at,
    }
