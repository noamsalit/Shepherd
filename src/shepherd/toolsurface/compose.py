"""What this build is composed of, in one place (ADR-7, T18-3).

Two module-global surfaces, composed by one call: the **registry** of
capabilities, and the **ring** those capabilities' events are published through.
Both are module-global by ADR-7, both have to be empty before the server can
serve a request, and the composition root should have to know that once rather
than twice.

`daemons/controld.py` used to spell this out: five imports and five calls to
register the ten M1 tools, then `freeze_registry()`. That is not logic, which is
why ADR-1's cap allowed it — but the cap is a proxy for "no logic in a
composition root", and the file sat at exactly 150 lines with nothing to spare,
so the next wiring change could not be additive. The ledger's own second option
was this: move tool registration into `toolsurface/`, where capabilities live.

`controld` keeps the *order*, which is the part that is a contract: compose,
then freeze, then bind (ADR-7 — the registry is written by one thread at
startup and read-only from the moment the server can serve a request).

`ingest` is a parameter rather than something composed here: the socket's name
belongs to `daemons/sessiond.py`, and L4 does not import L6.

`publish_result` lives here for the same reason the registration does: ADR-4
says `signals/` produces events and the composition publishes them, and a loop
over a result is not an *order*. The daemon keeps the order and hands this
function to the lanes as their `on_result`.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import utc_now
from shepherd.core.fold_types import FoldResult
from shepherd.core.mailbox import MailboxCounts
from shepherd.core.master import MasterRuntime
from shepherd.core.runner import RunnerHandle, RunnerRefusal, SessionSpec
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.engines.claude_code.registry import claude_config_dir, scan_registry
from shepherd.engines.claude_code.spawn import (
    BINARY_NAME,
    capabilities,
    resolve_binary,
    spawn_argv,
)
from shepherd.engines.claude_code.version import DRIFT_RECORD_NAME
from shepherd.host.base import HostPlatform, SocketPlan
from shepherd.orchestration.dialog_keys import SidecarState
from shepherd.orchestration.lifecycle import reconcile_owned_panes
from shepherd.orchestration.mailbox import sweep_pending
from shepherd.orchestration.master_turn import TurnDriver
from shepherd.runner.base import Runner
from shepherd.runner.local import RUNNER_NAME, CommandResult, LocalRunner, make_run_argv
from shepherd.runner.tmux_cmd import DEFAULT_SOCKET, permitted_commands, permitted_sockets
from shepherd.signals.discovery_loop import WAITING_STATUS
from shepherd.signals.replay import DIFF_DIRNAME
from shepherd.store.db import Store
from shepherd.toolsurface.approvals import ApprovalStore, build_authorizer
from shepherd.toolsurface.client import bind_master_client
from shepherd.toolsurface.registry import freeze_registry, install_chokepoint, reset_registry
from shepherd.toolsurface.stream import publish, reset_stream
from shepherd.toolsurface.tools_engine import register_engine_tools
from shepherd.toolsurface.tools_hooks import register_hook_tools
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.tools_m3 import kill as kill_session_now
from shepherd.toolsurface.tools_terminal import kill_landed
from shepherd.toolsurface.tools_m3 import register_m3_tools
from shepherd.toolsurface.tools_master import autonomy_level, register_master_tools
from shepherd.toolsurface.tools_projects import register_project_tools
from shepherd.toolsurface.tools_rename import register_rename_tool
from shepherd.toolsurface.tools_replay import register_replay_tool
from shepherd.toolsurface.types import AuditSink

__all__ = [
    "LOGS_DIRNAME",
    "PANE_SINK_DIRNAME",
    "PROJECTS_DIRNAME",
    "RUNNER_SOCKET_KEY",
    "SINK_PROGRAM",
    "M3Wiring",
    "M4Wiring",
    "build_runner",
    "close_master",
    "compose_tool_surface",
    "log_root",
    "mailbox_sweep",
    "master_plane",
    "publish_result",
    "reset_master_plane",
    "run_fork",
    "runner_socket",
    "sidecar_reader",
    "transcript_root",
]

#: The `app_state` key naming the tmux socket this build drives (RD1, D49).
#: `runner/tmux_cmd.py` owns the default and the forbidden name; this owns only
#: where an operator's override is kept.
RUNNER_SOCKET_KEY = "runner_socket"

#: Where `pipe-pane` sinks live, under the host's runtime dir. tmux runs that
#: argument through `sh -c`, so the path is confined to characters no shell
#: re-reads (`local.py::SINK_PATH_RE` refuses anything else).
PANE_SINK_DIRNAME = "panes"

#: The only program this exec site's shell-executing tmux verbs may name besides
#: the engine's own binary: `runner/local.py`'s `pipe-pane -o -t <target>
#: 'cat >> <sink>'` (T8-3). Spelled **here** rather than in `runner/`, because
#: `permitted_commands` is a fact the exec site's *constructor* holds — which is
#: this module — and `runner/` may not spell the engine's binary at all (T8-1).
SINK_PROGRAM = "cat"


@dataclass(frozen=True)
class M3Wiring:
    """What the composition hands back to the **order** the root keeps.

    Two members, and both are things the root cannot build for itself without
    naming a capability: the one `Runner` this process has, and T14's mailbox
    sweep, which rides the discovery loop's existing cadence (T23).
    """

    runner: Runner
    sweep: Callable[[], MailboxCounts]


@dataclass(frozen=True)
class M4Wiring(M3Wiring):
    """M3's two, plus the approval store this process gates through.

    **No `threads` field.** ADR-M4-6 revision 1 had the composition return a
    thread for the root to add to its own tuple — unimplementable as written,
    because `shutdown, bound = threading.Event(), threading.Event()` is created
    at `controld.py:82`, *six lines after* `compose_tool_surface` returns at 76:
    a thread built in here could never receive the event that stops it, and
    `shut_down` would report a hung thread on every shutdown while the socket
    was never unlinked (M1's stale-socket failure, re-introduced). With Track C
    cut and the master lazy (RD6) **M4 starts no thread at boot**, so the
    problem dissolves rather than being repaired.

    The approvals are handed back because §12's rail and clause 20's shutdown
    are both about *this* process's pending cards, and a second `ApprovalStore`
    would be a second set of them.
    """

    approvals: ApprovalStore


@dataclass(frozen=True)
class _MasterPlane:
    """What shutdown has to undo, held where ADR-7 already holds the registry.

    A module-level holder rather than a field on `M4Wiring`, for the reason
    ADR-M4-6 gives: `daemons/shutdown.py` is handed a thread tuple and a
    `close_store`, and `controld.stop()` is one line the root cannot grow. The
    registry and the stream ring are module-global for the same reason and by
    the same decision, so this is the shape that is already here rather than a
    new one.
    """

    driver: TurnDriver
    approvals: ApprovalStore


_PLANE: _MasterPlane | None = None


def reset_master_plane() -> None:
    """Back to no master. The composition's own start, and every test's."""
    global _PLANE
    _PLANE = None


def master_plane() -> _MasterPlane | None:
    """What this process composed, or `None` in a process that never did."""
    return _PLANE


def close_master(timeout_s: float) -> int:
    """Clause 20: end the turn in flight and free everything it blocked.

    Called by `daemons/shutdown.py`, which is where ADR-M4-6 puts the step —
    `shutdown.py` is not a composition root, so it has lines to spend and
    `controld.py` does not have to grow one.

    **Two withdrawals, and the second is not the first repeated.**
    `interrupt_master()` withdraws by *that turn's* id and then interrupts
    (ADR-M4-3, in that order because P2 measured that the interrupt frees
    nothing); `wait_for_turn` is the driver's own bounded wait for the worker,
    handed shutdown's timeout rather than the driver's 30 s default, so the
    runtime's `close()` has run by the time this returns. What is left after it
    is every card raised by a caller that is not the master — §12's rail, a
    page, the CLI — and a worker parked in front of one of those would wait its
    full 600 s while the process it is waiting for exits (P2: no cancellation
    reaches a running handler, so our own compare-and-set is the only release).
    So the sweep is by turn, over what is still pending, and it returns how many
    it freed — a number, because "shutdown left somebody blocked" must be a fact
    the exit line can say rather than a silence.

    A process that never composed has nothing to close, and says so with `0`.
    """
    plane = _PLANE
    if plane is None:
        return 0
    plane.driver.interrupt_master()
    plane.driver.wait_for_turn(timeout_s)
    return sum(
        plane.approvals.withdraw_all(turn_id)
        for turn_id in {
            approval.turn_id
            for approval in plane.approvals.pending()
            if approval.turn_id is not None
        }
    )


#: Where the engine keeps per-project transcripts, under its own config dir
#: (ADR-2 — never Shepherd's).
PROJECTS_DIRNAME = "projects"

#: Shepherd's own log root under `HostDirs.data_dir` (ADR-2, D25). The stop log
#: is `<data>/logs/stops/` and the replay diffs are its sibling
#: `<data>/logs/replay/` — one root, resolved from the host and nowhere else, so
#: a test puts both under `tmp_path` by handing in a different host.
LOGS_DIRNAME = "logs"


def log_root(host: HostPlatform) -> Path:
    """Shepherd's own log root: `HostDirs.data_dir`, and nothing else (ADR-2).

    One resolver rather than two spellings, because two callers have to agree
    about it: the `replay` tool *reads* this directory and the stop log
    *writes* into it, and a second spelling would be a `replay` that reports
    zero records against a log that is filling up. No environment variable, no
    `Path.home()`, no cwd — a test relocates both by handing in a host.
    """
    return host.dirs().data_dir / LOGS_DIRNAME


def transcript_root(engine_config_dir: Path | None = None) -> Path:
    """The **engine's** transcript root, never Shepherd's own dirs (ADR-2).

    The same resolution the discovery lane already performs in `discovery_pass`
    (`signals/discovery_loop.py`): the injected throwaway when there is one,
    else the engine's own `claude_config_dir()`. It is one function rather than
    a second resolver so that a test which points the registry scan at a
    throwaway config dir points the stop path's transcript reads at the same
    one — which is exactly what `tests/daemons/test_controld.py` needs to drive
    a stop without touching this host's real `~/.claude`.
    """
    config_dir = engine_config_dir if engine_config_dir is not None else claude_config_dir()
    return config_dir / PROJECTS_DIRNAME


def runner_socket(store: Store) -> str:
    """The tmux socket this build drives, from `app_state` (RD1, D49).

    A stored value rather than a constant because the socket is an operator's
    fact — and `DEFAULT_SOCKET` when nothing set one, which is an answer rather
    than a `None` a caller has to interpret. A non-string stored under the key is
    **ignored**, not coerced: the guard at the exec site refuses an unpermitted
    socket anyway, and a coerced `"None"` would be a socket name nobody chose.
    """
    stored = store.get_app_state(RUNNER_SOCKET_KEY)
    return stored if isinstance(stored, str) and stored else DEFAULT_SOCKET


def build_runner(store: Store, host: HostPlatform) -> LocalRunner:
    """The **one** `LocalRunner` this process has (T23's Allowed Scope).

    One, because a second would be a second socket's worth of state: the pane a
    tool writes to and the pane the reconcile adopted have to be the same pane.

    `spawn_argv` binds the engine's words to the binary **at spawn time**
    (`orchestration/spawn.py`'s own note asks this of the composition): an
    unresolvable `claude` is then E-M3-14's refusal, carrying the `PATH` it
    really searched, instead of a pane that dies 127 with no exit code.
    """
    socket = runner_socket(store)

    def words(spec: SessionSpec, *, frame_bytes: int) -> list[str]:
        return spawn_argv(spec, resolve_binary(), frame_bytes=frame_bytes)

    return LocalRunner(
        socket=socket,
        run_argv=make_run_argv(
            permitted_sockets(socket), permitted_commands(SINK_PROGRAM, BINARY_NAME)
        ),
        launch=host.detached_launch(),
        now=utc_now,
        spawn_argv=words,
        record_anomaly=lambda anomaly: store.bump_anomaly(str(anomaly.kind.value)),
        sink_dir=host.dirs().runtime_dir / PANE_SINK_DIRNAME,
    )


def run_fork(argv: list[str], *, timeout_ms: int) -> CommandResult:
    """`ask()`'s process seam: `RunArgv` plus the deadline (T15's note).

    The kill has to happen where the child is held — `subprocess.run(timeout=)`
    kills before it raises — or a fleet machine leaks one process per question.
    Every failure crosses back as a `RunnerRefusal`, which is the one exception
    `ask_session` is written to receive.
    """
    try:
        completed = subprocess.run(argv, capture_output=True, check=False, timeout=timeout_ms / 1000)
    except (OSError, subprocess.SubprocessError) as error:
        raise RunnerRefusal(f"the fork could not be run to completion: {error}") from error
    return CommandResult(rc=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def sidecar_reader(config_dir: Path) -> Callable[[str], SidecarState]:
    """D44's second source: is the engine's own live record waiting on a dialog?

    `SidecarState`'s docstring puts this resolution on the caller, and the caller
    is the composition: `toolsurface/` may not spell the engine's field names, so
    the one status word comes from `signals/`'s single spelling of it rather than
    a second literal here. An id no sidecar carries is `ABSENT` — a first-class
    answer, never read as "nothing is waiting" (principle 5).
    """

    def read(engine_session_id: str) -> SidecarState:
        entries, _ = scan_registry(config_dir)
        for entry in entries:
            if entry.session_id == engine_session_id:
                return (
                    SidecarState.WAITING
                    if entry.status == WAITING_STATUS
                    else SidecarState.NOT_WAITING
                )
        return SidecarState.ABSENT

    return read


def mailbox_sweep(store: Store, runner: Runner) -> Callable[[], MailboxCounts]:
    """D45's second delivery trigger, as one callable the discovery loop runs.

    The handles are read per sweep rather than held: a pane adopted by the
    startup reconcile, or bound by a spawn one second ago, is in the row and not
    in any map this process built at startup.
    """

    def sweep() -> MailboxCounts:
        handles: dict[str, RunnerHandle] = {}
        for session_id in store.sessions_with_pending():
            row = store.get_owned_session(session_id)
            if row is not None and row.runner_handle is not None:
                handles[session_id] = row.runner_handle
        return sweep_pending(store=store, runner=runner, now=utc_now, handles=handles)

    return sweep


def compose_tool_surface(
    store: Store,
    host: HostPlatform,
    db_path: Path,
    ingest: SocketPlan,
    build_master: Callable[[Store, str], MasterRuntime],
    audit_sink: AuditSink,
) -> M4Wiring:
    """Register this build's capabilities and freeze the registry. Once, at start.

    The ring is emptied here too: it is the other module-global this process
    serves from, and a composition that left the previous one's backlog in it
    would replay a dead run's events to the first page that connected.

    **The two surfaces are still module-global** (ADR-7) and neither is handed
    back. What is returned is the M3 wiring the *root* has to carry to a thread
    it already starts: the runner (so nothing else builds a second one) and the
    mailbox sweep (so it rides the 2.0 s cadence rather than a fourth thread).
    The signature is unchanged, so `controld.py:74` becomes an assignment on the
    same physical line and the root grows by **zero** lines (T23).

    Order, and why it is this one: the reconcile runs **before** the freeze
    because an orphaned pane holds one of §11's total-cap slots whether or not
    anything knows of it, and the cap is asked on the first spawn — which cannot
    arrive before the server binds, which cannot happen before the freeze.

    **The two M4 parameters are the two things L4 may not say** (ADR-M4-6).
    `build_master` is `shepherd.master`, which is L5 and upward; `audit_sink` is
    built over a `RotatingJsonlLog`, and DP3 pins `toolsurface/audit.py` as the
    *single* L4 importer of `shepherd.logs`. Both arrive from `daemons/plane.py`
    the way `ingest` already arrives as a plan rather than as a socket name.

    **The gate and the sink go in together or not at all** (DP13): one call,
    two required arguments, and `install_chokepoint` is the only writer — so *a
    gate with no audit log* is not a state this build can hold. Until this line
    runs, `invoke()` fails closed above `local_read`, which makes an uncomposed
    process loud rather than silently ungated.
    """
    reset_registry()
    reset_stream()
    reset_master_plane()
    # Built **before** the read tools register, because `fleet_summary` is
    # handed its `pending` (D2 of the M1-M4 QA pass): §12's rail has three
    # sources and the projection saw two. One store, read by the gate that
    # raises the cards and by the rail that shows them — a second would be a
    # second set of cards, which `M4Wiring` already refuses.
    approvals = ApprovalStore(now=utc_now)
    register_read_tools(
        store, projects_root=transcript_root(), pending_approvals=approvals.pending
    )
    register_hook_tools(entry=build_hook_entry(ingest, host.hook_dispatch(ingest)))
    register_engine_tools(db_path=db_path, drift_record_path=db_path.parent / DRIFT_RECORD_NAME)
    log_dir = log_root(host)
    register_replay_tool(store, log_dir, log_dir / DIFF_DIRNAME)

    runner = build_runner(store, host)
    engine_config_dir, binary = claude_config_dir(), _binary()
    pane_driver = _reconcile(store, runner, runner_socket(store))
    engine = capabilities(pane_driver_available=pane_driver)
    register_m3_tools(
        store=store,
        runner=runner,
        now=utc_now,
        sleep=time.sleep,
        publish=_publish,
        ensure_server=runner.ensure_server,
        # `None` is the decision T10-R2 asks somebody to type: the engine's own
        # `$CLAUDE_CONFIG_DIR`-or-`$HOME` resolution is the production answer,
        # and naming a directory here would be Shepherd choosing one for it.
        engine_config_home=None,
        run_fork=run_fork,
        binary=binary,
        projects_root=transcript_root(),
        can_fork=engine.can_fork and bool(binary),
        read_sidecar=sidecar_reader(engine_config_dir),
    )
    register_rename_tool(
        store=store, runner=runner, now=utc_now, config_dir=engine_config_dir, capabilities=engine
    )
    # D57's project lifecycle (T3.2, completed at T3.3).
    #
    # The `kill` injection is the shipped `kill_session` path — one
    # implementation, so a session stopped by a project delete is recorded
    # exactly the way a session stopped by the button is (`lifecycle.py`'s
    # write-before-kill order, which is what survives a crash). It is passed to
    # the **tool**, never to a `store/` verb: `delete_project` calls it between
    # `plan_project_delete` and `commit_project_delete`, on the calling thread
    # and inside no transaction. Handing it to a write verb instead is what
    # deadlocked the writer thread and kept this verb out of T3.1.
    #
    # `kill_session_now` answers `no_pane(...)` — no `"killed"` key — for any
    # session it has no runner handle for, which is every *attached* one. That
    # `False` is the truth: the commit half then refuses rather than deleting a
    # live session's rows.
    #
    # Reading that answer is `kill_landed`'s job and it lives **beside the
    # producer** (T3.4). It was spelled here, inside this closure: a string key
    # in two files, in a function no test could reach, so a rename on the
    # producer side would have left this adapter answering `False` forever and
    # silently.
    def kill_for_delete(session_id: str) -> bool:
        return kill_landed(
            kill_session_now(
                store=store, runner=runner, now=utc_now, publish=_publish, session_id=session_id
            )
        )

    # `_publish` is the same adapter M3's set and the approval store are handed
    # (D7): a project mutation that reaches no ring is a project mutation no
    # second tab ever learns about, which is what QA run 4 measured — six 200s,
    # zero frames, with the reader proved live first.
    register_project_tools(
        store=store, kill=kill_for_delete, publish=_publish, now=utc_now
    )

    driver = TurnDriver(
        store=store,
        # The turn id the driver mints reaches the runtime that will raise
        # approvals under it (RD-T4-2). Nothing else in this process knows
        # which turn is live, and a key that matches nothing would leave every
        # blocked handler riding its 600 s deadline with the tree still green.
        build_master=lambda turn_id: build_master(store, turn_id),
        publish=publish,
        withdraw_turn_approvals=approvals.withdraw_all,
        now=utc_now,
    )
    register_master_tools(
        store=store,
        approvals=approvals,
        audit_root=log_root(host),
        send_turn=driver.send_turn,
        interrupt_master=driver.interrupt_master,
        now=utc_now,
    )
    install_chokepoint(
        build_authorizer(
            approvals,
            lambda: autonomy_level(store),
            publish,
            lambda kind: _bump(store, kind),
            utc_now,
        ),
        audit_sink,
    )
    bind_master_client(
        withdraw_approval=approvals.withdraw,
        withdraw_turn_approvals=approvals.withdraw_all,
        autonomy_level=lambda: int(autonomy_level(store)),
    )
    _install_plane(_MasterPlane(driver=driver, approvals=approvals))
    freeze_registry()
    return M4Wiring(
        runner=runner, sweep=mailbox_sweep(store, runner), approvals=approvals
    )


def _install_plane(plane: _MasterPlane) -> None:
    global _PLANE
    _PLANE = plane


def _bump(store: Store, kind: AnomalyKind) -> None:
    """The counter the gate is handed. The store's verb takes the `str` the
    schema holds, and a member passed straight to it would write the enum's
    repr into a column every reader compares against the value."""
    store.bump_anomaly(str(kind.value))


def _binary() -> str:
    """The engine binary, or `""` when this `PATH` has none (C1, E-M3-14).

    A value rather than a raise: `ask()` degrades to the mailbox without one, and
    a composition that refused to start because `claude` is not installed would
    take the fleet page down with it.
    """
    try:
        return resolve_binary()
    except RunnerRefusal:
        return ""


def _reconcile(store: Store, runner: Runner, socket: str) -> bool:
    """T12's startup reconcile, and the pane-driver **fact** D-5 needs.

    The driver either answered its listing or refused; that answer is what
    `capabilities(pane_driver_available=)` is handed, exactly as `admission.py`
    hands it the same observation. Never a literal — a `True` typed here would
    make the degrade dead code on every host.
    """
    try:
        reconcile_owned_panes(
            store=store,
            runner=runner,
            now=utc_now,
            runner_name=RUNNER_NAME,
            socket=socket,
        )
    except RunnerRefusal:
        return False
    return True


def _publish(event: StreamEvent) -> None:
    """`stream.publish` returns how many subscribers took the event; a capability
    has no use for that number, and the seam it is handed to says `None`. The
    count is dropped **here**, once, rather than by widening that seam."""
    publish(event)


def publish_result(result: FoldResult) -> None:
    """ADR-4: `signals/` produces events, the composition publishes them."""
    for event in result.events:
        publish(event)
