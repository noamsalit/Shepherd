"""T25 — what M4 adds to the composition, driven through the shipped composition.

**The seam is `compose_tool_surface` itself, and that is the whole point of this
file.** M4 shipped six mechanisms with passing tests and no caller — the
chokepoint, the master client, the master tools, the turn-id supplier, the turn
driver and `resume()` — and the router's own register says what that is worth:
*a mechanism with passing tests and no caller counts as evidence at acceptance
while doing nothing.* Every check here therefore composes the real surface and
observes it from outside, never by installing the thing it is asserting.

**The audit proof is the one only this file can make (P-M4-4).** T5's
integration test drove a real `RotatingJsonlLog` and said plainly that *"the
shipped composition calls this sink"* was not a statement any test on its file
list could make. An audit check that injects its own sink proves the collector
works; it does not prove the shipped path reaches it. So the sink here is
`plane.audit_sink(store, host)` — shipped code — the call is a real destructive
call through `invoke()`, and the record is read back off the disk by the one
reader.

Two disciplines, because both have been paid for in this repo:

* **no literal count.** The master's tool names are enumerated by registering
  them into an empty registry and comparing sets; the rule is written into the
  check, so a tool added to `tools_master.py` widens both sides at once.
* **arrival before absence, and the arrival is mutated.** Where a check ends in
  an emptiness, the same predicate is first shown reporting something.
"""

from __future__ import annotations

import ast
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import MasterRuntime
from shepherd.daemons import plane
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface import client, compose
from shepherd.toolsurface.approvals import Approval, ApprovalOutcome
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.registry import chokepoint, invoke, register, registered_tools
from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY, register_master_tools
from shepherd.toolsurface.types import Audience, CallerContext, Failure, ToolDef

NOW = "2026-09-17T10:00:00Z"

#: Every wait in this file is bounded. A mutant that hangs is not a red, and two
#: M4 tasks paid for learning that; ten seconds is far beyond the time any of
#: these take and far below the 600 s approval deadline, which is exactly the
#: gap `test_the_withdrawal_beats_the_deadline_rather_than_waiting_for_it` is
#: about.
ARRIVAL_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class World:
    """Everything `compose_tool_surface` takes, all of it under `tmp_path`."""

    store: Store
    host: ScriptedHost
    db_path: Path
    ingest: SocketPlan
    built_for: list[str]

    def compose(self) -> compose.M4Wiring:
        """The shipped call, with the shipped plane on both sides of it.

        `build_master` is wrapped only to record the turn id it was handed —
        the runtime it returns is a double, because building a real
        `AgentSDKMaster` here would put a vendor subprocess behind a unit test.
        What is asserted is the **wiring**, and the wiring is the plane's.
        """

        def build(store: Store, turn_id: str) -> MasterRuntime:
            self.built_for.append(turn_id)
            runtime: MasterRuntime = _IdleMaster()
            return runtime

        return compose.compose_tool_surface(
            self.store,
            self.host,
            self.db_path,
            self.ingest,
            build,
            plane.audit_sink(self.store, self.host),
        )


class _IdleMaster:
    """A `MasterRuntime` that opens a turn and ends it without an event.

    Enough to prove the driver was wired: nothing here is a claim about what a
    runtime does, which is `tests/master/`'s and the contract suite's.
    """

    def __init__(self) -> None:
        self.closed = 0

    def configure(self, tools: tuple[object, ...], system_prompt: str) -> None:
        pass

    async def _stream(self) -> object:  # pragma: no cover - typing only
        raise AssertionError

    def send(self, text: str) -> object:
        async def stream() -> object:
            if False:  # pragma: no cover - an empty async generator
                yield None

        return stream()

    def resume(self, master_session_id: str) -> None:
        pass

    def interrupt(self) -> None:
        pass

    def capabilities(self) -> object:  # pragma: no cover
        raise AssertionError("no capability is read here")

    def close(self) -> None:
        self.closed += 1


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    # K3: the engine config dir is a throwaway, so nothing here can even read
    # the real `~/.claude`, let alone write beside it.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    runtime_dir = tmp_path / "run"
    host = ScriptedHost(
        host_dirs=HostDirs(
            data_dir=tmp_path / "data",
            config_dir=tmp_path / "config",
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
            detail="no supervisor on this host",
            manageable=False,
            start_limit_note="five restarts in ten seconds then the unit is refused",
        ),
        login=LoginPersistence(
            enabled=None,
            mechanism="none observed",
            detail="no persistence mechanism could be read on this host",
        ),
        observed_at=NOW,
    )
    db_path = tmp_path / "data" / "shepherd.db"
    store = open_store(db_path)
    try:
        yield World(
            store=store,
            host=host,
            db_path=db_path,
            ingest=host.control_socket("sessiond"),
            built_for=[],
        )
    finally:
        client.reset_master_client()
        compose.reset_master_plane()
        store.close()


def as_master(correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=Audience.MASTER, caller_id="master", correlation_id=correlation_id
    )


def wait_for_card(wiring: compose.M4Wiring) -> Approval:
    """Block until exactly one card is pending, bounded. Arrival, not a sleep."""
    deadline = threading.Event()
    for _ in range(int(ARRIVAL_TIMEOUT_S * 200)):
        pending = wiring.approvals.pending()
        if pending:
            return pending[0]
        deadline.wait(0.005)
    raise AssertionError(f"no approval was raised within {ARRIVAL_TIMEOUT_S}s")


# ----- the chokepoint (T6) ----------------------------------------------------


def test_the_chokepoint_is_installed_by_the_composition(world: World) -> None:
    """T6's row on the "no caller" register, closed and asserted.

    Until something calls `install_chokepoint`, `invoke()` fails closed above
    `local_read` (DP13) — so the whole milestone's gate is inert in production
    and green in every test. Arrival before absence: the chokepoint is asserted
    **absent** first, so `is not None` afterwards is a change this composition
    made rather than a leftover from another check's install.
    """
    assert chokepoint() is None, "the registry arrived with a gate already installed"

    world.compose()

    assert chokepoint() is not None


def test_an_uncomposed_process_refuses_the_destructive_call_the_composed_one_gates(
    world: World,
) -> None:
    """DP13's fail-closed rule, as the other half of the check above.

    The *same* call, in a process that never composed, is refused; composed, it
    reaches the gate and raises a card. That is what makes "the chokepoint is
    installed" a statement about behaviour rather than about a module global.
    """
    register(_a_destructive_tool())

    refused = invoke("kill_session", {"session_id": "s-1"}, as_master("c-1"))

    assert refused.ok is False
    assert refused.failure is Failure.UNAVAILABLE


def _a_destructive_tool() -> ToolDef:
    from shepherd.toolsurface.types import BlastClass

    return ToolDef(
        name="kill_session",
        description="the shipped name, in an uncomposed process",
        input_schema={
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=lambda args, ctx: {"killed": True},
        audiences=frozenset({Audience.MASTER, Audience.HUMAN}),
    )


# ----- P-M4-4: the shipped composition writes to a real log -------------------


def test_the_composed_surface_writes_to_a_real_log(world: World) -> None:
    """P-M4-4. The sink is shipped code, the call is real, the log is on disk.

    A destructive call as the master is `_ASK` at level 2, so this also drives
    the gate end to end: the card is waited for (arrival), approved from this
    thread while the call blocks on another, and the record is then read back
    by `read_audit_records` — the single reader — from the host's own log root.

    **Goes red if the sink is never set**, which is the mutation that makes
    every other audit test a test of its own wiring (M3's `session.js` defect,
    one layer down).
    """
    wiring = world.compose()
    answered: list[object] = []

    def call_it() -> None:
        answered.append(invoke("kill_session", {"session_id": "no-such"}, as_master("turn-1")))

    caller = threading.Thread(target=call_it, name="blocked-call", daemon=True)
    caller.start()

    card = wait_for_card(wiring)
    assert card.tool == "kill_session"
    assert wiring.approvals.decide(card.id, ApprovalOutcome.APPROVED) is True
    caller.join(ARRIVAL_TIMEOUT_S)
    assert not caller.is_alive(), "the approved call never came back"

    records = read_audit_records(compose.log_root(world.host), 10)
    assert [record["tool"] for record in records] == ["kill_session"]
    assert records[0]["decision"] == "allow"
    assert records[0]["approved_by"] == "user"
    assert records[0]["correlation_id"] == "turn-1"


def test_a_denied_call_is_written_to_the_same_real_log(world: World) -> None:
    """The gate's other exit. One record per decided call, never per allowed
    call — a log that recorded only what ran would be an audit log that cannot
    answer *"what did it try"*."""
    wiring = world.compose()
    answered: list[object] = []

    def call_it() -> None:
        answered.append(invoke("kill_session", {"session_id": "no-such"}, as_master("turn-2")))

    caller = threading.Thread(target=call_it, name="blocked-call", daemon=True)
    caller.start()

    card = wait_for_card(wiring)
    assert wiring.approvals.decide(card.id, ApprovalOutcome.REJECTED) is True
    caller.join(ARRIVAL_TIMEOUT_S)
    assert not caller.is_alive()

    records = read_audit_records(compose.log_root(world.host), 10)
    assert [record["decision"] for record in records] == ["deny"]


# ----- the master tools (T23) and the routes ----------------------------------


def test_the_master_tools_are_registered_by_the_composition(world: World) -> None:
    """T23's row: the ten `ToolDef`s the plan says *"registered by the
    composition root (T25)"*.

    The expected set is **enumerated**, by registering them into an empty
    registry and reading the names back, so a tool added to `tools_master.py`
    widens both sides of this equality at once and no number in this file has
    to be maintained. Arrival: the enumeration is asserted non-empty first.
    """
    from shepherd.toolsurface.registry import reset_registry

    from shepherd.core.clock import utc_now
    from shepherd.toolsurface.approvals import ApprovalStore

    reset_registry()
    register_master_tools(
        store=world.store,
        approvals=ApprovalStore(),
        audit_root=world.host.dirs().data_dir,
        send_turn=lambda text: None,  # type: ignore[arg-type,return-value]
        interrupt_master=lambda: False,
        now=utc_now,
    )
    expected = set(registered_tools())
    assert expected, "register_master_tools registered nothing at all"
    reset_registry()

    world.compose()

    assert expected <= set(registered_tools())


def test_every_post_route_resolves_to_a_registered_tool(world: World) -> None:
    """The shipped rule, asked of the **composed** registry rather than of a
    registry a check assembled: a route whose tool never arrived answers a
    browser with a 500 while every unit test stays green."""
    from shepherd.web.routes import POST_ROUTES

    world.compose()
    registered = registered_tools()

    assert [name for name in POST_ROUTES.values() if name not in registered] == []
    # Arrival: the table really was read and really does name capabilities.
    assert "kill_session" in POST_ROUTES.values()
    assert [name for name in ("no_such_tool",) if name not in registered] != []


# ----- the master client (T16) ------------------------------------------------


def test_the_master_client_is_bound_by_the_composition(world: World) -> None:
    """§T16-7's row. `bind_master_client` was called from nowhere, so every
    member of the client was reachable only from its own test file.

    Driven through the client's public functions against the composed store: an
    unbound client raises `MasterClientUnbound`, which is what makes this an
    arrival rather than a shape.
    """
    wiring = world.compose()

    # A live read of the store, not a value captured at composition: D8's
    # toggle takes effect on the next call, and `set_autonomy_level` is a tool
    # this same registry holds.
    world.store.set_app_state(AUTONOMY_LEVEL_KEY, 3)
    assert client.autonomy_level() == 3
    world.store.set_app_state(AUTONOMY_LEVEL_KEY, 2)
    assert client.autonomy_level() == 2
    # …and the withdrawal reaches the composition's own approval store.
    caller = threading.Thread(
        target=lambda: invoke("kill_session", {"session_id": "x"}, as_master("turn-3")),
        name="blocked-call",
        daemon=True,
    )
    caller.start()
    card = wait_for_card(wiring)
    assert client.withdraw_turn_approvals("turn-3") == 1
    caller.join(ARRIVAL_TIMEOUT_S)
    assert not caller.is_alive(), "the withdrawn call never came back"
    assert card.id not in [pending.id for pending in wiring.approvals.pending()]
    # …and the withdrawal was **counted**, through the counter the composition
    # handed the gate (D54). The member is enumerated off `AnomalyKind` rather
    # than written out, and it is compared by `.value` because that is the
    # spelling every reader of `app_state` compares against — a counter handed
    # the member itself would write a repr nothing matches.
    counted = world.store.list_anomaly_counts()
    members = {member.value: member for member in AnomalyKind}
    assert set(counted) <= set(members), sorted(set(counted) - set(members))
    assert counted.get(AnomalyKind.APPROVAL_WITHDRAWN.value) == 1


# ----- the turn driver, and the turn id (RD-T4-2) -----------------------------


def test_the_composed_send_tool_opens_a_turn_through_the_driver(world: World) -> None:
    """The last link of the chain, driven from the tool a person clicks.

    `master_send` → `TurnDriver.send_turn` → `build_master(turn_id)`. The id the
    factory was handed is asserted against the id the tool reported, so a plane
    keyed on anything else — a fresh ULID, a constant, the caller id — is red
    here rather than silently unreleasable.
    """
    world.compose()

    answered = invoke(
        "master_send",
        {"text": "hello"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-4"),
    )

    assert answered.ok is True
    payload = answered.data
    assert isinstance(payload, dict)
    assert world.built_for == [payload["turn_id"]]


def test_no_master_is_built_before_a_turn_asks_for_one(world: World) -> None:
    """RD6: the master is lazy and this build starts no thread at boot.

    The composition is the whole of boot, so a runtime constructed inside it
    would be a vendor subprocess started by `shepherd-controld` starting.
    """
    wiring = world.compose()

    assert world.built_for == []
    assert wiring.approvals.pending() == ()


# ----- the layer rule ---------------------------------------------------------


def test_compose_does_not_import_the_master_package() -> None:
    """§5.0: L4 may not import L5. The runtime arrives as a factory instead.

    By AST over the source text, and every spelling: `import`, `from … import`
    and an alias. Arrival: the same reader is shown finding the imports that
    *are* there, so `== []` is an emptiness it could have broken.
    """
    source = Path(compose.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "shepherd.toolsurface.registry" in imported, "the reader read nothing"
    assert [name for name in sorted(imported) if name.split(".")[:2] == ["shepherd", "master"]] == []
    assert [name for name in sorted(imported) if name.split(".")[:2] == ["shepherd", "logs"]] == []


# ----- the project lifecycle (T3.2) -------------------------------------------


def test_the_project_tools_are_registered_by_the_composition(world: World) -> None:
    """T3.2's row: D57's lifecycle, reachable in a **composed** process.

    The expected set is enumerated the way the master tools above are — by
    registering into an empty registry and reading the names back — so a verb
    added to `tools_projects.py` widens both sides of this equality at once and
    no list in this file has to be maintained.

    The call at the end is a `local_read`, which the gate lets through at every
    autonomy level. That is deliberate: the point of this line is that the
    *registration happened before the freeze*, and driving a
    `local_destructive` verb here would park the test on the real approval
    deadline to prove something `tests/toolsurface/test_tools_projects.py`
    already proves behind the shipped gate.
    """
    from shepherd.toolsurface.registry import RegistryFrozen, invoke, reset_registry
    from shepherd.toolsurface.tools_projects import (
        PROJECT_TOOL_NAMES,
        register_project_tools,
    )

    reset_registry()
    register_project_tools(store=world.store)
    expected = set(registered_tools())
    assert expected == set(PROJECT_TOOL_NAMES), sorted(expected)
    reset_registry()

    world.compose()

    assert expected <= set(registered_tools())
    answered = invoke(
        "list_repos", {"project_id": "unassigned"}, as_master("cid-projects")
    )
    assert answered.ok, (answered.error, answered.failure)
    assert answered.data == {"repos": []}

    # …and the registry really did freeze, so the registration above was not a
    # late one that merely happened to work. A second `register` after the
    # composition is the refusal ADR-7 exists for.
    with pytest.raises(RegistryFrozen):
        register_project_tools(store=world.store)
