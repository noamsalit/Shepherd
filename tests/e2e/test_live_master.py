"""T26 — one real master turn through the shipped composition, and the teardown.

**What only this file can prove.** Everything before it drove a double
somewhere. T25 said so in its own words: *"No real `AgentSDKMaster` was driven.
`test_the_shipped_runtime_satisfies_the_seam` builds one and closes it … but
every check that runs a turn uses a double."* Here a real `claude` runs behind
the real `compose_tool_surface`, through the real `install_chokepoint` gate,
driven by the real `TurnDriver`, and the audit record it produces is read back
off a real log by the single reader. T5 proved the encoder; T25 proved the
shipped composition writes; this proves it happens **when a live master calls a
tool**.

**Two turns, and both are the shipped path.**

1. A read call and a destructive call against a session row this test created.
   The read is `local_read`, so §11's table allows it by *policy* and no card is
   raised. The destructive one is `local_destructive` at level 2 on the `MASTER`
   audience, so the gate raises a card, the master's tool worker parks in
   `await_decision`, and this thread presses Approve. Two audit records, one per
   call, with `policy` and `user` on them respectively.
2. A second destructive call, and this time the turn is **interrupted** while
   the card is pending. `TurnDriver.interrupt_master()` withdraws by the turn's
   id and only then touches the engine (ADR-M4-3), so the outcome is `withdrawn`
   and the moment it was released is asserted **strictly before the card's own
   `deadline_at`** — the live half of P-M4-22. A timeout cannot satisfy that,
   because a timeout *is* the deadline.

**Every live assertion is arrival-first, and the arrival is an assertion.**
M3's lane shipped `count == 1` in a world where the second writer could never
run — a pass that could not fail. M4's own T21 recorded `"tools": []`, which is
also what a broken mount produces. So: the mounted set is non-empty before it is
compared; the engine's pid is found and asserted **alive** before it is asserted
gone; the audit log is asserted non-empty and to carry both turns' ids before a
per-turn row set is compared; the card is waited for and asserted present before
anything is said about its outcome. Nothing here is a count typed into the file:
the expected audit rows are built from the tool names the restriction chose and
the blast classes are read back off the shipped registry.

**The blast radius, stated because this file starts a real engine.**

* an explicit `--settings` file inside `tmp_path`, so nothing the engine writes
  can reach the operator's own; the per-test `settings_guard` in `conftest.py`
  digests `~/.claude/settings.json` before and after **every** test here;
* every inherited `CLAUDE*` / `ANTHROPIC*` / `AI_AGENT` variable deleted before
  the subprocess exists, so the run cannot measure the session it runs in;
* a working directory that is not the repo, thrown away with `tmp_path`;
* **no tmux server, and a throwaway socket for the one argv there is.** The
  claim *"no tmux at all"* would be **false and was measured to be**:
  `compose_tool_surface`'s startup reconcile calls `runner.list_owned_panes()`,
  which execs `tmux -L <socket> list-sessions`. So the runner socket this build
  drives is written into `app_state` as a throwaway `shepherd-m4-…` name, and
  `make_run_argv(permitted_sockets(that), …)` is then an exec site that refuses
  any other — never the user's socket, which `permitted_sockets` refuses at
  construction, and never the product's `shepherd-runner`, which a test must
  not share. `list-sessions` contacts a server and never starts one, and the
  socket set before and after this run is the evidence. The one destructive
  tool mounted acts on a row with **no `runner_handle`**, so `handle_for`
  answers `None` and `kill()` returns `no_pane` without an argv being built at
  all;
* every wait is bounded and liveness is read from `/proc`, **never** from a
  signal (CLAUDE.md, 2026-09-17 — that rule cost a host).

**RD10: a restricted tool set, and exactly one destructive tool.** *"A live
master holding the whole destructive surface is a test that can act on the
operator's fleet."* So `daemons/plane.master_tools` is substituted, in process,
with a filter over the **real** projection: the two shipped `ToolDef`s named
below and nothing else. Every other thing the plane does — the turn id, the
counter, the withdrawal, the model read from `app_state`, the frozen prompt, the
resume — is shipped code running unmodified. The two substitutions are listed in
`SUBSTITUTIONS` and asserted, so neither can grow quietly.
"""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pytest

from shepherd.core.clock import parse_stamp, utc_now
from shepherd.core.ids import new_ulid
from shepherd.core.states import Origin
from shepherd.daemons import plane
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.core.master import ExportedTool
from shepherd.master import sdk_master
from shepherd.master.sdk_tools import TOOL_PREFIX, prefixed_names
from shepherd.orchestration.master_turn import MASTER_SESSION_KEY, TurnStarted
from shepherd.runner.tmux_cmd import DEFAULT_SOCKET, FORBIDDEN_SOCKET, permitted_sockets
from shepherd.store.db import open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface import client as master_client
from shepherd.toolsurface import compose
from shepherd.toolsurface.approvals import Approval, ApprovalOutcome, ApprovalStore
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.registry import registered_tools
from shepherd.toolsurface.types import BlastClass

from .conftest import (
    INHERITED_PREFIXES,
    LIVE_MODEL,
    _engine_pid,
    real_config_dir,
    settings_digest,
)

# ---------------------------------------------------------------------------
# What this run is made of
# ---------------------------------------------------------------------------

#: The two shipped capabilities the live master is given, and no others (RD10).
#: Named rather than derived — *"pick any destructive tool"* would make the run
#: non-reproducible and the audit rows unpredictable — but their **classes** are
#: read back off the shipped registry at test time, so a reclassification is a
#: red here rather than a silently different scenario.
READ_TOOL = "get_session"
DESTRUCTIVE_TOOL = "kill_session"

#: The two in-process substitutions this run makes, and the whole list of them.
#: Asserted as an equality by `test_live_a_master_turn_gates_audits_and_withdraws`
#: so a third cannot be added without a line here — the same mechanism T22 uses
#: for its allow-list, and for the same reason: the interesting claim is *what is
#: shipped*, so what is not has to be enumerable.
SUBSTITUTIONS: frozenset[str] = frozenset(
    {
        "daemons.plane.master_tools -> the two tools above (RD10)",
        "daemons.plane.AgentSDKMaster -> the same class with an explicit --settings",
    }
)

#: The runner socket written into `app_state` for this run. **Never `shepherd`**,
#: which `permitted_sockets` refuses at construction, and never the product's
#: `shepherd-runner`. Nothing in this lane starts tmux — the mounted destructive
#: tool acts on a handle-less row — so this is the belt for the day something
#: does.
THROWAWAY_RUNNER_SOCKET = "shepherd-m4-t26"

#: The engine binary's own name. The SDK spawns `…/claude_agent_sdk/_bundled/claude`
#: when `cli_path` is `None` (the plane's answer), so `argv[0]`'s **basename** is
#: what identifies one — by basename and never by spelling, which is T8-2's rule
#: about the tmux binary applied to this one.
ENGINE_ARGV0 = "claude"

#: Bounds. Every one of them is a ceiling rather than a measurement, and every
#: wait in this file has one: *a mutant that hangs is not a red*, and neither is
#: a live engine that stopped answering.
TURN_TIMEOUT_S = 300.0
CARD_TIMEOUT_S = 180.0
PID_GONE_TIMEOUT_S = 30.0
RELEASE_TIMEOUT_S = 30.0
POLL_S = 0.02

#: Where this test writes what a human reads (RD-T17-11: this task's path, never
#: a shared one).
SCRATCH = Path(__file__).resolve().parents[2] / "scratchpad" / "m4-t26"


def turn_text(read_name: str, destructive_name: str, session_id: str) -> str:
    """Turn 1's instruction, built from the **prefixed** names actually mounted.

    Derived rather than written out: the prefix is `sdk_tools.TOOL_PREFIX`'s and
    a second spelling of it here would be a prompt that asks for a tool this
    build does not mount — which the model would answer by not calling anything,
    and which would read exactly like a broken gate.
    """
    return (
        "Do exactly the following, in order, and nothing else.\n"
        f'1. Call the tool `{read_name}` once, with session_id "{session_id}".\n'
        f'2. Call the tool `{destructive_name}` once, with session_id "{session_id}".\n'
        "3. Reply with the single word DONE.\n\n"
        "Call each of those two tools exactly once. Call no other tool. Do not"
        " retry a tool call, whatever it answers: its answer is data for me, not"
        " a problem for you to solve. Do not ask me anything."
    )


def interrupted_turn_text(destructive_name: str, session_id: str) -> str:
    """Turn 2's instruction: one gated call, which this test never approves."""
    return (
        f'Call the tool `{destructive_name}` once, with session_id "{session_id}",'
        " and then reply with the single word DONE. Call it exactly once, call no"
        " other tool, and do not retry it."
    )


# ---------------------------------------------------------------------------
# The two ledgers: engine processes and tmux sockets
# ---------------------------------------------------------------------------


def pid_cmdline(pid: int) -> tuple[str, ...]:
    """One process's argv, read from `/proc`. `()` if it is already gone.

    Read as **bytes and split on NUL**, because that is what `/proc` holds; a
    reader that split on whitespace would merge a word containing a space and
    then report a basename nothing has.
    """
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ()
    return tuple(
        word.decode("utf-8", "replace") for word in raw.split(b"\x00") if word
    )


def engine_pids() -> frozenset[int]:
    """Every `claude` on this host right now, by `argv[0]`'s basename.

    **Basename, not spelling** (T8-2's rule, one binary over): the SDK spawns
    its own bundled `…/_bundled/claude` rather than `PATH`'s, so a rule keyed on
    the string `"claude"` would see the operator's Remote Control sessions and
    miss the one this lane started — an emptiness that means nothing.

    `/proc` and never a signal. `os.kill(pid, 0)` is the idiom and it is the one
    this repo refuses: a probe that signals is a probe that can end something,
    and on 2026-09-17 one did, to pid 1.
    """
    found: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        argv = pid_cmdline(int(entry.name))
        if argv and PurePosixPath(argv[0]).name == ENGINE_ARGV0:
            found.add(int(entry.name))
    return frozenset(found)


def tmux_socket_dir() -> Path:
    """Where tmux keeps this user's sockets. Read, never written.

    The **socket set** is the teardown ledger and not `tmux -L … ls`: reading it
    off the directory contacts no server, builds no argv and names nothing, so
    the check that the lane left no tmux behind cannot itself be the thing that
    starts one. CLAUDE.md's invariant is the socket, and this is the socket.
    """
    return Path(f"/tmp/tmux-{os.getuid()}")


def tmux_sockets(directory: Path) -> frozenset[str]:
    """The socket names in `directory`. Sockets only — a stray regular file in
    there is not a tmux server and counting it would be an invented leak."""
    if not directory.is_dir():
        return frozenset()
    return frozenset(entry.name for entry in directory.iterdir() if entry.is_socket())


# ---------------------------------------------------------------------------
# One live run
# ---------------------------------------------------------------------------


@dataclass
class TurnRecord:
    """Everything one turn left behind that a check reads."""

    turn_id: str
    card_tool: str | None = None
    card_id: str | None = None
    card_summary: str | None = None
    deadline_at: str | None = None
    outcome: ApprovalOutcome | None = None
    released_at: str | None = None
    ended: bool = False


@dataclass
class LiveRun:
    """The whole lane: two turns, the ledgers, and what came off disk."""

    turns: tuple[TurnRecord, ...]
    mounted: tuple[str, ...]
    records: tuple[Mapping[str, object], ...]
    engine_pids: tuple[int, ...]
    engine_argv: Mapping[int, tuple[str, ...]]
    survivors: tuple[int, ...]
    pids_before: frozenset[int]
    pids_after: frozenset[int]
    sockets_before: frozenset[str]
    sockets_after: frozenset[str]
    digest_before: str
    digest_after: str
    conversation_id: str | None
    stored_session_id: object
    anomalies: Mapping[str, int]
    runner_socket: str
    """What the composed exec site was permitted to name — read back off the
    store through the shipped resolver, never the constant this file typed."""
    inits: tuple[Mapping[str, object], ...]
    """Each turn's `system/init`, recorded for the human_verify checkpoint. No
    check here asserts a field of it: that is T22's claim and repeating it here
    under a live banner is M3's clause-10 defect."""


@dataclass
class _Built:
    """The runtimes the shipped plane built, in the order it built them."""

    runtimes: list[sdk_master.AgentSDKMaster] = field(default_factory=list)


def _scripted_host(base: Path) -> ScriptedHost:
    """A host whose every directory is under `base`. Shepherd's own dirs are
    thrown away; the engine's are its own and are never Shepherd's (ADR-2)."""
    runtime_dir = base / "run"
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=base / "data",
            config_dir=base / "config",
            runtime_dir=runtime_dir,
        ),
        socket_plan=SocketPlan(
            path=runtime_dir / "sessiond.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(
            command=f"scripted-send {runtime_dir / 'sessiond.sock'}",
            requires=("scripted-send",),
            available=True,
            reason="scripted fixture",
        ),
        supervision_plan=Supervision(
            kind="foreground",
            detail="no supervisor in this lane",
            manageable=False,
            start_limit_note="none",
        ),
        login=LoginPersistence(
            enabled=None,
            mechanism="none observed",
            detail="not read in this lane",
        ),
        observed_at=utc_now(),
    )


def _await_card(
    approvals: ApprovalStore,
    built: _Built,
    seen: dict[int, tuple[str, ...]],
    timeout_s: float,
) -> Approval:
    """Block until exactly one card is pending — and find the engine on the way.

    Two observations in one bounded loop, because they happen in the same
    window: the card arrives while the engine is alive, so this is where the
    **arrival** half of P-M4-17 is taken. A pid found here is asserted alive at
    the instant it is recorded, so the absence asserted later is the absence of
    something that was demonstrably there.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _note_engines(built, seen)
        pending = approvals.pending()
        if pending:
            return pending[0]
        time.sleep(POLL_S)
    raise AssertionError(
        f"no approval card was raised within {timeout_s}s — the live master never"
        f" reached the gate. engines seen: {sorted(seen)}"
    )


def _note_engines(built: _Built, seen: dict[int, tuple[str, ...]]) -> None:
    """Record every engine pid this run has had, with its argv, once each."""
    for runtime in list(built.runtimes):
        pid = _engine_pid(runtime)
        if pid is None or pid in seen:
            continue
        argv = pid_cmdline(pid)
        assert argv, (  # the arrival, as an assertion and not a comment
            f"engine pid {pid} was reported by the transport and is already gone"
            " from /proc, so nothing was ever observed alive"
        )
        seen[pid] = argv


def _wait_until_resolved(
    approvals: ApprovalStore, approval_id: str, timeout_s: float
) -> str:
    """Block until `approval_id` is no longer pending, then stamp the moment.

    The stamp is taken the instant the card leaves `pending()` and before
    anything else can interfere, which is what makes *"released before the
    deadline"* a statement about the release rather than about this test's own
    scheduling.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if approval_id not in {approval.id for approval in approvals.pending()}:
            return utc_now()
        time.sleep(POLL_S)
    raise AssertionError(
        f"the approval {approval_id} was still pending {timeout_s}s after the"
        " interrupt — the withdrawal never reached it"
    )


@pytest.fixture(scope="module")
def live_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveRun]:
    """Two real turns through the shipped composition, torn down here.

    Module-scoped because a live engine is the expensive part and the checks
    below read different facets of **one** run: two runs would be two subjects
    for one claim, which is the defect T22's own fixture note is about.
    """
    base = tmp_path_factory.mktemp("t26-live-master")
    settings = base / "flag-settings.json"
    settings.write_text("{}", encoding="utf-8")
    workdir = base / "work"
    workdir.mkdir()

    digest_before = settings_digest()
    pids_before = engine_pids()
    sockets_before = tmux_sockets(tmux_socket_dir())

    db_path = base / "data" / "shepherd.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    host = _scripted_host(base)
    store = open_store(db_path)
    built = _Built()
    seen: dict[int, tuple[str, ...]] = {}
    turns: list[TurnRecord] = []

    with pytest.MonkeyPatch.context() as patch:
        try:
            # §17's row, through the shipped reader: the live lane runs on the
            # cheapest model, and it says so where a settings page would.
            store.set_app_state(plane.MASTER_MODEL_KEY, LIVE_MODEL)
            store.set_app_state(compose.RUNNER_SOCKET_KEY, THROWAWAY_RUNNER_SOCKET)

            workspace = store.upsert_workspace("t26-live", str(workdir))
            session_id = new_ulid()
            store.create_owned_session(
                session_id=session_id,
                # Engine-bound because the store insists: `create_owned_session`
                # refuses an unbound row for any origin but `ask_fork`, since an
                # unbound spawn row lets the discovery sweep register the
                # engine's id as a *second* row for one pane. The uuid names no
                # session that exists — nothing in this lane spawns one.
                engine_session_id=str(uuid.uuid4()),
                workspace_id=workspace.id,
                repo_id=None,
                cwd=str(workdir),
                started_at=utc_now(),
                origin=Origin.ORCHESTRATOR,
                parent_session_id=None,
                depth=0,
                ephemeral=True,
                title="a throwaway row for T26",
                title_source="brief",
                # **No handle, and that is the safety property.** `handle_for`
                # answers `None`, so the destructive tool's handler returns
                # `no_pane` and never builds a tmux argv at all.
                handle=None,
                model=LIVE_MODEL,
                effort=None,
            )

            # The composition's own reads of the engine's config dir are bound
            # here, at call time, so they land on a throwaway. The variable is
            # then removed with the rest of the scrub, because an isolated
            # config dir has no credentials and the engine would die
            # `Not logged in` (M1 Finding 3) — isolation and authentication are
            # mutually exclusive on this host.
            patch.setenv("CLAUDE_CONFIG_DIR", str(base / "engine-config"))

            restricted = _restrict(plane.master_tools)
            patch.setattr(plane, "master_tools", restricted)
            patch.setattr(plane, "AgentSDKMaster", _recording(settings, built))

            wiring = compose.compose_tool_surface(
                store, host, db_path, host.control_socket("sessiond"),
                plane.build_master, plane.audit_sink(store, host),
            )
            mounted = prefixed_names(restricted())

            for name in list(os.environ):
                if name.startswith(INHERITED_PREFIXES):
                    patch.delenv(name, raising=False)
            patch.chdir(workdir)

            surface = compose.master_plane()
            assert surface is not None, "the composition installed no master plane"
            driver = surface.driver

            # Selected by name rather than by position: the projection's order
            # is the registry's and a positional read would silently swap the
            # two the day a tool is registered earlier, which is a different
            # scenario wearing this one's assertions.
            read_name = next(name for name in mounted if name.endswith(READ_TOOL))
            destructive_name = next(
                name for name in mounted if name.endswith(DESTRUCTIVE_TOOL)
            )

            # ----- turn 1: a policy-allowed read and an approved destructive --
            first = driver.send_turn(turn_text(read_name, destructive_name, session_id))
            assert isinstance(first, TurnStarted), first
            one = TurnRecord(turn_id=first.turn_id)
            turns.append(one)
            card = _await_card(wiring.approvals, built, seen, CARD_TIMEOUT_S)
            one.card_tool, one.card_id = card.tool, card.id
            one.card_summary, one.deadline_at = card.summary, card.deadline_at
            assert wiring.approvals.decide(card.id, ApprovalOutcome.APPROVED) is True
            one.outcome = ApprovalOutcome.APPROVED
            one.ended = driver.wait_for_turn(TURN_TIMEOUT_S)
            _note_engines(built, seen)

            # ----- turn 2: the same call, withdrawn by an interrupt ----------
            second = driver.send_turn(interrupted_turn_text(destructive_name, session_id))
            assert isinstance(second, TurnStarted), second
            two = TurnRecord(turn_id=second.turn_id)
            turns.append(two)
            other = _await_card(wiring.approvals, built, seen, CARD_TIMEOUT_S)
            two.card_tool, two.card_id = other.tool, other.id
            two.card_summary, two.deadline_at = other.summary, other.deadline_at
            assert driver.interrupt_master() is True, (
                "interrupt_master() reported no live turn while a card of that"
                " turn's was pending"
            )
            two.released_at = _wait_until_resolved(
                wiring.approvals, other.id, RELEASE_TIMEOUT_S
            )
            two.outcome = wiring.approvals.await_decision(other.id, 0.0)
            two.ended = driver.wait_for_turn(TURN_TIMEOUT_S)
            _note_engines(built, seen)

            conversation = (
                built.runtimes[-1].conversation_id() if len(built.runtimes) > 1 else None
            )
            stored_session = store.get_app_state(MASTER_SESSION_KEY)
            records = read_audit_records(compose.log_root(host), 50)
            anomalies = dict(store.list_anomaly_counts())
            socket_named = compose.runner_socket(store)
            inits = tuple(
                init
                for init in (runtime.system_init() for runtime in built.runtimes)
                if init is not None
            )
        finally:
            compose.close_master(TURN_TIMEOUT_S)
            master_client.reset_master_client()
            compose.reset_master_plane()
            store.close()

    gone = time.monotonic() + PID_GONE_TIMEOUT_S
    while any(pid_cmdline(pid) for pid in seen) and time.monotonic() < gone:
        time.sleep(0.1)

    run = LiveRun(
        turns=tuple(turns),
        mounted=mounted,
        records=records,
        engine_pids=tuple(sorted(seen)),
        engine_argv=dict(seen),
        survivors=tuple(pid for pid in sorted(seen) if pid_cmdline(pid)),
        pids_before=pids_before,
        pids_after=engine_pids(),
        sockets_before=sockets_before,
        sockets_after=tmux_sockets(tmux_socket_dir()),
        digest_before=digest_before,
        digest_after=settings_digest(),
        conversation_id=conversation,
        stored_session_id=stored_session,
        anomalies=anomalies,
        runner_socket=socket_named,
        inits=inits,
    )
    _record(run)
    yield run


def _restrict(
    projection: Callable[[], tuple[ExportedTool, ...]],
) -> Callable[[], tuple[ExportedTool, ...]]:
    """RD10. The **real** `MASTER` projection, narrowed to the two tools above.

    A filter over the shipped projection rather than a hand-built list: the
    `ExportedTool`s a live master is handed are then the ones the registry
    actually produced — same description, same schema, same three fields — and
    the only thing this run changes is *how many* of them there are.
    """

    def restricted() -> tuple[ExportedTool, ...]:
        chosen = {READ_TOOL, DESTRUCTIVE_TOOL}
        return tuple(
            exported for exported in projection() if exported.name in chosen
        )

    return restricted


def _recording(
    settings: Path, built: _Built
) -> Callable[..., sdk_master.AgentSDKMaster]:
    """The shipped `AgentSDKMaster`, with an explicit `--settings` and a ledger.

    **The only difference from production is the settings path**, and it is the
    isolation belt the brief requires of anything that starts a real engine:
    `daemons/plane.build_master` passes no `settings` at all (D42's block is
    `None`), so a live run driven straight off the plane would let the engine
    read the operator's own file. `setting_sources=[]` already excludes user
    scope — P4 measured that — but two levers kept separate is what the probe
    harness recommends and what T21 and T22's live runs both did.

    The ledger is what lets the pid be found: the seam has no pid reader and one
    added for a live check would be a member with no production caller (§T21-10).
    """

    def make(**wiring: object) -> sdk_master.AgentSDKMaster:
        runtime = sdk_master.AgentSDKMaster(settings=str(settings), **wiring)  # type: ignore[arg-type]
        built.runtimes.append(runtime)
        return runtime

    return make


def _record(run: LiveRun) -> None:
    """What a human reads at the checkpoint (§18: *"do not trust it"*)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "live-run.json").write_text(
        json.dumps(
            {
                "mounted": list(run.mounted),
                "turns": [
                    {
                        "turn_id": turn.turn_id,
                        "card_tool": turn.card_tool,
                        "card_id": turn.card_id,
                        "card_summary": turn.card_summary,
                        "deadline_at": turn.deadline_at,
                        "released_at": turn.released_at,
                        "outcome": None if turn.outcome is None else str(turn.outcome),
                        "ended": turn.ended,
                    }
                    for turn in run.turns
                ],
                "audit_records": [dict(record) for record in run.records],
                "engine_pids": list(run.engine_pids),
                "engine_argv": {
                    str(pid): list(argv) for pid, argv in run.engine_argv.items()
                },
                "survivors": list(run.survivors),
                "claude_pids_before": sorted(run.pids_before),
                "claude_pids_after": sorted(run.pids_after),
                "tmux_sockets_before": sorted(run.sockets_before),
                "tmux_sockets_after": sorted(run.sockets_after),
                "settings_sha256_before": run.digest_before,
                "settings_sha256_after": run.digest_after,
                "conversation_id": run.conversation_id,
                "stored_master_session_id": run.stored_session_id,
                "anomaly_counts": dict(run.anomalies),
                "runner_socket": run.runner_socket,
                "system_init": [dict(init) for init in run.inits],
                "substitutions": sorted(SUBSTITUTIONS),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def rows_for(run: LiveRun, turn_id: str) -> list[tuple[str, str, str]]:
    """One turn's audit rows as `(tool, decision, approved_by)`, sorted.

    Read off what `read_audit_records` returned — the **single** reader, over
    the log the shipped composition wrote — and stringified rather than cast:
    a record whose field is missing reads as `"None"` and fails the comparison
    loudly instead of raising a `KeyError` that says nothing about which row.
    """
    return sorted(
        (str(record.get("tool")), str(record.get("decision")), str(record.get("approved_by")))
        for record in run.records
        if record.get("correlation_id") == turn_id
    )


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_live_a_master_turn_gates_audits_and_withdraws(live_run: LiveRun) -> None:
    """The milestone's central claim, read off disk.

    A real `claude`, behind the real `compose_tool_surface`, through the real
    gate, writing a real audit log — and the records below were produced by a
    **live master calling a tool**, which is the one thing no earlier task
    could say. T5 proved the encoder against a sink it built; T25 proved the
    shipped composition reaches the sink, with a double where the master should
    be. This is the sentence with no double left in it.

    Arrival, in this order, each one an assertion:

    1. the mounted set is non-empty and is exactly the restriction (a broken
       mount produces an empty set just as faithfully as a locked one — T21's
       `"tools": []`);
    2. the two tools' **blast classes** are what §11's table was consulted
       about, read back off the shipped registry rather than typed here;
    3. the audit log is non-empty and carries both turns' correlation ids;
    4. only then is each turn's row set compared.
    """
    assert live_run.mounted, "nothing was mounted, so every equality below is vacuous"
    # Compared whole and in both directions, against the **shipped** prefix
    # constant: a membership test would pass with a third tool mounted beside
    # them, which is exactly the surface RD10 refuses a live master.
    expected = {f"{TOOL_PREFIX}{name}" for name in (READ_TOOL, DESTRUCTIVE_TOOL)}
    assert set(live_run.mounted) == expected, {
        "mounted": sorted(live_run.mounted),
        "expected": sorted(expected),
    }
    assert len(live_run.mounted) == len(expected), live_run.mounted

    assert SUBSTITUTIONS == frozenset(
        {
            "daemons.plane.master_tools -> the two tools above (RD10)",
            "daemons.plane.AgentSDKMaster -> the same class with an explicit --settings",
        }
    ), sorted(SUBSTITUTIONS)

    assert live_run.records, (
        "the audit log is empty, so the live master reached no tool at all"
    )
    one, two = live_run.turns
    correlations = {str(record.get("correlation_id")) for record in live_run.records}
    assert {one.turn_id, two.turn_id} <= correlations, sorted(correlations)

    # Turn 1 — one record per call, and the attribution is the whole point.
    # `policy` is §11's table letting a `local_read` through with no card;
    # `user` is `approvals.py`, the **only** producer of that value in the
    # build, saying a person pressed Approve. A log that said `user` for the
    # read would be the overclaim K23 exists to name.
    assert rows_for(live_run, one.turn_id) == sorted(
        [
            (READ_TOOL, "allow", "policy"),
            (DESTRUCTIVE_TOOL, "allow", "user"),
        ]
    ), rows_for(live_run, one.turn_id)
    assert one.card_tool == DESTRUCTIVE_TOOL, one.card_tool
    assert one.ended, "turn 1's thread never ended within its bound"

    # Turn 2 — the same call, withdrawn. One record, and it is a **denial**:
    # a log that recorded only what ran could not answer *"what did it try"*.
    assert rows_for(live_run, two.turn_id) == [
        (DESTRUCTIVE_TOOL, "deny", "withdrawn")
    ], rows_for(live_run, two.turn_id)
    assert two.outcome is ApprovalOutcome.WITHDRAWN, two.outcome

    # P-M4-22, live: released, not timed out. A timeout **is** the deadline, so
    # a release strictly before it is a fact no timeout can produce. Compared as
    # instants through the one parser, never as strings.
    assert two.released_at is not None and two.deadline_at is not None
    released, deadline = parse_stamp(two.released_at), parse_stamp(two.deadline_at)
    assert released is not None and deadline is not None, (two, )
    assert released < deadline, {
        "released_at": two.released_at,
        "deadline_at": two.deadline_at,
    }
    assert two.ended, "turn 2's thread never ended within its bound"


@pytest.mark.live
def test_live_the_shipped_registry_classified_the_two_calls(live_run: LiveRun) -> None:
    """The classes §11's table was consulted about, read off the shipped registry.

    The check above asserts `policy` for one call and `user` for the other. That
    is only the *right* answer if the two tools really are a `local_read` and a
    `local_destructive` — otherwise it is two arbitrary strings agreeing with
    two other arbitrary strings. This is the half that makes the attribution
    mean something, and it goes red the day either tool is reclassified, which
    is exactly when the scenario stopped being the scenario.

    It reads the registry **this run composed**, so it is also an arrival: a
    composition that registered neither tool fails here rather than three
    assertions later.
    """
    assert live_run.records, "no live call was made, so there is nothing to classify"
    tools = registered_tools()
    assert {READ_TOOL, DESTRUCTIVE_TOOL} <= set(tools), sorted(tools)
    assert tools[READ_TOOL].blast_class is BlastClass.LOCAL_READ
    assert tools[DESTRUCTIVE_TOOL].blast_class is BlastClass.LOCAL_DESTRUCTIVE


@pytest.mark.live
def test_live_no_engine_process_survives_the_lane(live_run: LiveRun) -> None:
    """**P-M4-17**. Arrival first on the pid, then absence — and the sockets too.

    A runtime that never spawned anything would satisfy an emptiness check
    perfectly, so the order is: a pid was found off the transport **and asserted
    alive at that instant** while the turn ran, its argv was read from `/proc`
    and is the engine's, and only then is it asserted gone.

    The host-wide half is the set of every `claude` on this machine before and
    after. It is asserted as *"the after-set contains nothing the before-set did
    not"* rather than as a count: the operator's own Remote Control sessions are
    on this host and an assertion about how many there are fails whenever they
    open a terminal (F10, and CLAUDE.md's rule that names are not the invariant).

    The tmux ledger is the socket **set**, read off the socket directory. This
    lane starts no tmux at all — the one destructive tool acts on a handle-less
    row — so the claim is that the set did not grow.
    """
    assert live_run.engine_pids, (
        "no engine process was ever observed — the arrival never happened, so"
        " the absence below would be the absence of nothing"
    )
    for pid in live_run.engine_pids:
        argv = live_run.engine_argv[pid]
        assert argv, pid
        assert PurePosixPath(argv[0]).name == ENGINE_ARGV0, (pid, argv)
    assert not (set(live_run.engine_pids) & live_run.pids_before), (
        "an engine pid this lane recorded was already running before the lane"
        " started, so the ledger is reading somebody else's process"
    )

    assert live_run.survivors == (), {
        pid: live_run.engine_argv[pid] for pid in live_run.survivors
    }
    assert live_run.pids_after - live_run.pids_before == set(), sorted(
        live_run.pids_after - live_run.pids_before
    )
    assert live_run.sockets_after - live_run.sockets_before == set(), sorted(
        live_run.sockets_after - live_run.sockets_before
    )
    # …and the socket the composed exec site was permitted to name. The
    # emptiness above says no server appeared; this says the one tmux argv this
    # lane really does build could only ever have reached a throwaway. Read
    # back through the shipped resolver rather than trusted from the write.
    assert live_run.runner_socket == THROWAWAY_RUNNER_SOCKET, live_run.runner_socket
    assert live_run.runner_socket != FORBIDDEN_SOCKET
    assert live_run.runner_socket != DEFAULT_SOCKET
    assert live_run.runner_socket in permitted_sockets(live_run.runner_socket)


@pytest.mark.live
def test_the_socket_ledger_can_see_a_socket(tmp_path: Path) -> None:
    """The positive control for the check above, and it is load-bearing.

    `sockets_after - sockets_before == set()` is an emptiness, and an emptiness
    over a reader that can see nothing is a pass that cannot fail. M3's lane
    shipped exactly that shape. So the reader is pointed at a directory with a
    real unix socket bound in it and must report it — in `tmp_path`, binding
    nothing on the network and naming no tmux socket at all.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    assert tmux_sockets(empty) == frozenset()
    (empty / "not-a-socket").write_text("", encoding="utf-8")
    assert tmux_sockets(empty) == frozenset(), "a regular file was read as a server"

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(empty / "planted"))
        assert tmux_sockets(empty) == frozenset({"planted"}), sorted(tmux_sockets(empty))
    finally:
        listener.close()

    assert tmux_sockets(tmp_path / "nothing-here") == frozenset()


@pytest.mark.live
def test_live_the_settings_file_is_untouched(live_run: LiveRun) -> None:
    """P13, said once more in this file's own words, per test by the autouse guard.

    The guard in `conftest.py` digests `~/.claude/settings.json` before and after
    **every** test in this package, so a violation names the test that caused it.
    This is the run-wide statement: the same digest before the first turn and
    after the last, and it is asserted to be a **real digest** first — a reader
    that answered `"absent"` on both sides would compare equal and prove nothing.
    """
    assert live_run.digest_before != "absent", (
        "~/.claude/settings.json could not be read, so the equality below would"
        " be two absences agreeing with each other"
    )
    assert len(live_run.digest_before) == 64, live_run.digest_before
    assert live_run.digest_after == live_run.digest_before, {
        "before": live_run.digest_before,
        "after": live_run.digest_after,
    }
    assert settings_digest() == live_run.digest_before, settings_digest()
    assert (real_config_dir() / "settings.json").is_file()


@pytest.mark.live
def test_live_the_conversation_the_first_turn_saved_is_the_one_the_second_resumed(
    live_run: LiveRun,
) -> None:
    """D10's continuity, live — the half §T27-6 and T25 §T25-12 left open.

    `master_session_id` was *"persisted on every turn and resumed on none"*
    until T25 wired `plane.build_master` to read it back. T25 proved the line
    runs against a double. This is the live statement: turn 1 persisted an id
    the engine reported, and the runtime turn 2 was built with is continuing
    **that** conversation.

    Arrival: the stored id is asserted to be a non-empty string first, so the
    equality cannot be `None == None`.
    """
    stored = live_run.stored_session_id
    assert isinstance(stored, str) and stored, (
        "no master_session_id was persisted, so nothing could have been resumed"
    )
    assert live_run.conversation_id == stored, {
        "stored": stored,
        "second turn's runtime": live_run.conversation_id,
        "anomalies": dict(live_run.anomalies),
    }
