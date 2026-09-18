"""S2 — master spawns, session stops, wake carries it into the next turn.

The full chain nothing exercises: a master turn spawns a session → the session
stops → M2 classifies it → `wake.drain` picks it up → the **next** turn opens
with it in the summary. Four milestones, one line of causation, and every link
of it had its own passing tests written before the next link existed.

**What is driven.** `spawn_session` through the shipped `invoke()` as
`Audience.MASTER`, over the shipped `register_m3_tools` with a `ScriptedRunner`
in the `Runner` seam; then the shipped `signals.stop_lane.handle_stop` over a
**real captured transcript**; then `orchestration.wake.drain`; then
`orchestration.master_turn.TurnDriver`, whose `_opening_text` is the only drain
site in `src/`.

**The session id is the one the spawn returned.** Every later step is keyed off
`result.data["session_id"]`, never off a row a fixture wrote — which is the whole
of what makes this a chain rather than four fixtures in a row. That is the lying
implementation S2 was written to catch, and it is also how this file found the
defect below.

---

## The defect this scenario found, and the repair it now asserts

`store.reads.WAKE_ORIGIN` is `Origin.ORCHESTRATOR`, so `wake_candidates` selects
`WHERE origin = 'orchestrator'`. At the time this file was written **nothing in
`src/` ever created a session with that origin**: `tools_m3.SPAWN_ORIGIN` was one
module-level constant, `Origin.USER_UI`, written by *every* spawn including the
master's — so D31's wake set was structurally empty in production and every
existing test of it passed because each wrote its own `origin=ORCHESTRATOR` row
directly.

The repair is that `invoke()` now hands the handler the `CallerContext` it
already validated, and `spawn_session` reads the origin off **who asked**
(`tools_m3.SPAWN_ORIGIN_BY_ACTOR`, a total map over `ActorKind`). A master's
spawn writes `ORCHESTRATOR`; a human's still writes `USER_UI`, so the two cases
stay distinguishable and a person clicking the fleet page still does not wake the
master.

This file asserts the **chain**, end to end, over the session the master's own
`invoke("spawn_session")` returned — never a fixture row. The two constants are
imported, never respelled, so the check is about what the two modules agree on
rather than about a literal typed here.

*Lying implementations this now catches:*

* a wake set built from a fixture rather than from the session the master
  actually spawned — the id is the spawn's own, and the origin is read back off
  the row the tool wrote;
* an origin a caller could choose for itself, or one that makes a human's spawn
  wake the master — both audiences are driven through the same handler and the
  two rows are compared;
* a drain that stamps twice, or that stamps only when the set was non-empty —
  E-M4-18's row is driven and the stamp is compared across it;
* a second drain that hands back the same rows — driven, and asserted empty
  **after** the same reader was shown reporting something.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.clock import utc_now
from shepherd.core.runner import PaneState, ProcState
from shepherd.core.signals import Signal, SignalKind
from shepherd.core.states import Origin, Ownership
from shepherd.core.stops import Bucket
from shepherd.core.stream import StreamEvent
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import StopLog
from shepherd.orchestration import wake
from shepherd.orchestration.master_turn import TurnDriver, TurnStarted
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.signals import stop_lane
from shepherd.store.db import Store, open_store
from shepherd.store.reads import WAKE_ORIGIN
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import invoke, registered_tools, reset_registry
from shepherd.toolsurface.spawn_origin import SPAWN_ORIGIN_BY_ACTOR
from shepherd.toolsurface.tools_m3 import register_m3_tools
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    CallerContext,
    ToolArgs,
    actor_kind_of,
)

from ._gate import install_qa_chokepoint
from .conftest import IdleMaster, World

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes"
RUN = PROBES / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"
COPIES = PROBES / "2026-09-14-schemas" / "transcripts" / "copies"

#: A real captured transcript, and the engine session id inside it. Nothing here
#: invents a transcript shape — `docs/specs/data-schemas.md` is the rule and
#: these are the captures it was written from.
A_REAL_TRANSCRIPT = (
    COPIES / "-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl"
)

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
READY_CAPTURE = (RUN / "03-after-stop.ansi").read_bytes()

#: The engine's own `SessionEnd.reason`, projected to `signals`' neutral
#: `end_reason` key. `prompt_input_exit` is a **mapped, verified** row of
#: `stop_map.py`'s table (`StopReason.USER_EXITED`), which `stop_rules.py` puts
#: in `Bucket.UNFINISHED` — one of the two outcomes `wake_candidates` selects.
#: Chosen by reading the shipped tables rather than invented, and named here so
#: the choice is visible: `"other"` **defers** to the completeness split, which
#: read this capture as finished, and a wake test resting on that would have been
#: asserting a transcript's content rather than the wake rule.
STOP_END_REASON = "prompt_input_exit"

NOW = "2026-09-18T10:00:00Z"
STOPPED_AT = "2026-09-18T11:00:00Z"
LATER = "2026-09-18T12:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def ready_pane() -> PaneState:
    return read_pane(READY_CAPTURE, parse_pane_fields(LIVE_FIELDS), [])


@dataclass
class Spawner:
    """The M3 tool surface, behind the shipped gate, with a scripted runner."""

    store: Store
    runner: ScriptedRunner
    events: list[StreamEvent]


@pytest.fixture()
def spawner(store: Store, tmp_path: Path) -> Iterator[Spawner]:
    """`register_m3_tools` — the shipped registration — over a `ScriptedRunner`.

    Not `compose_tool_surface`, and the reason is named: the composition builds a
    `LocalRunner` whose exec site is real `tmux`, so a composed spawn starts a
    real pane on this host. The `Runner` seam is what `ScriptedRunner` exists
    for (§14.2, D36), everything above it here is shipped, and the gate is the
    shipped `build_authorizer` at production's own default level.
    """
    events: list[StreamEvent] = []
    runner = ScriptedRunner(
        panes=(ready_pane(),),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=READY_CAPTURE,
    )
    reset_registry()
    install_qa_chokepoint(AutonomyLevel.LEVEL_2)
    register_m3_tools(
        store=store,
        runner=runner,
        now=utc_now,
        sleep=lambda seconds: None,
        publish=events.append,
        ensure_server=lambda: None,
        engine_config_home=tmp_path / "engine-config",
        run_fork=lambda argv, *, timeout_ms: (_ for _ in ()).throw(
            AssertionError("no fork is taken in this scenario")
        ),
        binary="",
        projects_root=tmp_path / "projects",
        can_fork=False,
        read_sidecar=lambda engine_session_id: _absent(),
    )
    try:
        yield Spawner(store=store, runner=runner, events=events)
    finally:
        reset_registry()


def _absent() -> object:
    from shepherd.orchestration.dialog_keys import SidecarState

    return SidecarState.ABSENT


def as_master(correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=Audience.MASTER, caller_id="master", correlation_id=correlation_id
    )


def as_human(correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=Audience.HUMAN, caller_id="somebody-on-the-fleet-page",
        correlation_id=correlation_id,
    )


def spawn_through_invoke(spawner: Spawner, tmp_path: Path, ctx: CallerContext) -> str:
    """One `spawn_session` through the shipped `invoke()`, as whoever `ctx` says.

    Returns the id **the tool answered with**. Everything downstream keys off
    this and nothing else, which is S2's whole point. The caller is handed in as
    a `CallerContext` and **never** as an argument of the call: the arguments are
    the same mapping for every audience here, which is what makes "the origin
    came from who asked" an observation rather than a wish.
    """
    name = ctx.caller_id
    root = tmp_path / f"work-{name}"
    (root / "repo").mkdir(parents=True, exist_ok=True)
    workspace = spawner.store.upsert_workspace(name, str(root))

    assert "spawn_session" in registered_tools(), "the M3 tools did not register"
    result = invoke(
        "spawn_session",
        {"workspace_id": workspace.id, "cwd": str(root / "repo")},
        ctx,
    )
    assert result.ok is True, f"{name} could not spawn: {result.error}"
    data = result.data
    assert isinstance(data, dict), data
    session_id = data.get("session_id")
    assert isinstance(session_id, str) and session_id, f"the spawn returned no id: {data}"
    return session_id


def spawn_as_master(spawner: Spawner, tmp_path: Path) -> str:
    return spawn_through_invoke(spawner, tmp_path, as_master("s2-turn-1"))


def stop_it(store: Store, session_id: str, tmp_path: Path) -> object:
    """Drive M2's shipped stop lane over one row, by that row's own id.

    The transcript is a **real capture** (`docs/probes/2026-09-14-schemas/`),
    placed where the engine would have written it for this session's own
    `engine_session_id` — read back off the row rather than invented, so the
    evidence the classifier reads really belongs to the session in question.
    The prior snapshot is `store.snapshot(...)`, the store's own verb, never a
    `SessionSnapshot` assembled here: a hand-built prior is a state the
    application may never produce.
    """
    row = store.get_session(session_id)
    assert row is not None, f"{session_id} resolves to no row"
    projects = tmp_path / "projects" / "-a-lossy-slug"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / f"{row.engine_session_id}.jsonl").write_bytes(A_REAL_TRANSCRIPT.read_bytes())

    prior = store.snapshot(session_id)
    assert prior is not None, "the store has no snapshot of a row it just wrote"
    return stop_lane.handle_stop(
        signal=Signal(
            kind=SignalKind.SESSION_STOPPED,
            engine_session_id=row.engine_session_id,
            cwd=row.cwd,
            transcript_path="",
            received_at=STOPPED_AT,
            fields={"end_reason": STOP_END_REASON},
            raw_kind="opaque-to-the-lane",
        ),
        prior=prior,
        projects_root=tmp_path / "projects",
        received_at=STOPPED_AT,
        store=store,
        stop_log=StopLog(RotatingJsonlLog(tmp_path / "logs", "stops")),
        publish=lambda event: 0,
    )


# ----- the chain --------------------------------------------------------------


def test_the_master_spawns_and_the_row_carries_the_id_the_tool_answered_with(
    spawner: Spawner, tmp_path: Path
) -> None:
    """Link 1: `invoke("spawn_session")` as the master really creates the row.

    Arrival for everything below: without this, every later emptiness is the
    emptiness of a database nothing wrote to.
    """
    session_id = spawn_as_master(spawner, tmp_path)
    row = spawner.store.get_session(session_id)
    assert row is not None, "the id the tool returned resolves to no row"
    assert row.id == session_id
    assert row.ownership is Ownership.OWNED


def test_the_stop_lane_classifies_the_row_the_master_spawned(
    spawner: Spawner, tmp_path: Path
) -> None:
    """Link 2: M2 writes a verdict onto M3's row, keyed by M4's own id."""
    session_id = spawn_as_master(spawner, tmp_path)
    verdict = stop_it(spawner.store, session_id, tmp_path)
    assert verdict is not None, "the stop lane skipped the stop"

    row = spawner.store.get_session(session_id)
    assert row is not None
    assert row.ended_at is not None, "the row never ended"
    assert row.outcome is not None, "the row carries no outcome"
    assert row.stop_reason is not None, "the row was never classified"


def test_a_session_the_master_spawned_reaches_the_wake_set(
    spawner: Spawner, tmp_path: Path
) -> None:
    """**D1's repair, driven.** Link 3, over the master's own spawned row.

    `wake_candidates` selects `origin = WAKE_ORIGIN`; `spawn_session` now writes
    the origin `SPAWN_ORIGIN_BY_ACTOR` gives for **who asked**. Both are
    imported, never respelled — a literal here would be a third statement of a
    fact two modules already hold, and it would stop tracking them the moment
    either moved.

    The row reaching the wake set is the one `invoke()` answered with, and its id
    is compared; a fixture row could not satisfy this even if one existed, and
    `_a_row_that_can_wake` is deliberately not called anywhere in this test.
    """
    session_id = spawn_as_master(spawner, tmp_path)
    stop_it(spawner.store, session_id, tmp_path)
    row = spawner.store.get_session(session_id)
    assert row is not None

    assert row.origin is SPAWN_ORIGIN_BY_ACTOR[ActorKind.MASTER], (
        "the master's spawn did not write the origin the actor map gives it"
    )
    assert row.origin.value == WAKE_ORIGIN, (
        "spawn_session and wake_candidates disagree on an origin again — D1 is"
        " back and the wake set is structurally empty in production"
    )

    items = wake.peek(spawner.store)
    assert [item.session_id for item in items] == [session_id], (
        "the session the master spawned did not reach the wake set: "
        f"{[item.session_id for item in items]!r}"
    )
    assert items[0].bucket in (Bucket.UNFINISHED, Bucket.ERROR)
    assert items[0].why, "the wake item carries no `why` from M2's verdict"


def test_a_human_spawn_and_a_master_spawn_are_still_different_rows(
    spawner: Spawner, tmp_path: Path
) -> None:
    """The requirement the repair must not break: a person is not the master.

    D31 is explicit that the wake set is *master-spawned* sessions. Both spawns
    go through **one handler**, with the same argument mapping, differing only in
    the `CallerContext` `invoke()` was handed — so this is the property that the
    origin follows the caller and not the call.
    """
    human_session = spawn_through_invoke(spawner, tmp_path, as_human("s2-a-person"))
    master_session = spawn_as_master(spawner, tmp_path)
    stop_it(spawner.store, human_session, tmp_path)
    stop_it(spawner.store, master_session, tmp_path)

    human_row = spawner.store.get_session(human_session)
    master_row = spawner.store.get_session(master_session)
    assert human_row is not None and master_row is not None
    assert human_row.origin is SPAWN_ORIGIN_BY_ACTOR[ActorKind.HUMAN]
    assert human_row.origin is not master_row.origin, (
        "a human's spawn and the master's spawn now write the same origin"
    )
    assert human_row.origin.value != WAKE_ORIGIN, (
        "a person clicking the fleet page now wakes the master (D31)"
    )
    assert [item.session_id for item in wake.peek(spawner.store)] == [master_session]


def test_a_caller_cannot_choose_its_own_origin_by_argument(
    spawner: Spawner, tmp_path: Path
) -> None:
    """The second requirement: the origin is not a field the caller may set.

    Read off the tool's **own schema**, enumerated at test time rather than
    written out: whatever `spawn_session` accepts, no property of it is named for
    the origin, so `invoke()`'s argument validation refuses one. Driven as well
    as read, because a schema is a promise and `_argument_problem` is the keeper
    of it.
    """
    tool = registered_tools()["spawn_session"]
    properties = tool.input_schema["properties"]
    assert isinstance(properties, dict)
    assert not [key for key in properties if "origin" in key.lower()], properties

    root = tmp_path / "work-sneaky"
    (root / "repo").mkdir(parents=True, exist_ok=True)
    workspace = spawner.store.upsert_workspace("sneaky", str(root))
    refused = invoke(
        "spawn_session",
        {
            "workspace_id": workspace.id,
            "cwd": str(root / "repo"),
            "origin": str(Origin(WAKE_ORIGIN).value),
        },
        as_human("s2-sneaky"),
    )
    assert refused.ok is False, "a caller set its own origin and the call was accepted"


def test_the_origin_map_is_total_over_every_actor_kind_and_only_the_master_wakes(
    spawner: Spawner, tmp_path: Path
) -> None:
    """The map is a **property**, enumerated, never a list restated here.

    `ActorKind` is walked at test time, so a fifth member is a failing build
    rather than a `KeyError` inside a spawn that has already started a pane. And
    exactly one kind maps onto the wake origin — asserted as a set equality, so
    a second kind quietly joining the wake set is caught.
    """
    assert set(SPAWN_ORIGIN_BY_ACTOR) == set(ActorKind), (
        "SPAWN_ORIGIN_BY_ACTOR is not total over ActorKind"
    )
    wakes = {kind for kind, origin in SPAWN_ORIGIN_BY_ACTOR.items() if origin.value == WAKE_ORIGIN}
    assert wakes == {ActorKind.MASTER}, f"more than the master wakes the master: {wakes}"

    # …and the derivation really is the one the handler uses: the record's own
    # `actor_kind_of`, so M5's queue worker on the MASTER audience is a worker.
    worker = CallerContext(
        audience=Audience.MASTER,
        caller_id="a-queue-worker",
        correlation_id="s2-worker",
        actor_kind=ActorKind.WORKER,
    )
    assert actor_kind_of(worker) is ActorKind.WORKER
    session_id = spawn_through_invoke(spawner, tmp_path, worker)
    row = spawner.store.get_session(session_id)
    assert row is not None
    assert row.origin is SPAWN_ORIGIN_BY_ACTOR[ActorKind.WORKER]
    assert row.origin.value != WAKE_ORIGIN, (
        "a queue worker's spawn reaches the master's wake set; D31 routes those"
        " to the worker loop"
    )


def test_the_wake_machinery_itself_works_on_a_row_that_can_wake(
    spawner: Spawner, tmp_path: Path
) -> None:
    """The control for the chain above: the same reader, two routes to one set.

    One row registered through the store's own verb carrying `WAKE_ORIGIN`, and
    one the master really spawned through `invoke()`. Both reach the set, and the
    assertion is a **set equality** over ids rather than a count — a reader that
    dropped the spawned row and kept the fixture one is exactly the shape S2
    exists to catch, and it would satisfy any assertion about length.
    """
    session_id = spawn_as_master(spawner, tmp_path)
    stop_it(spawner.store, session_id, tmp_path)
    assert [item.session_id for item in wake.peek(spawner.store)] == [session_id]

    twin = _a_row_that_can_wake(spawner.store, tmp_path, spawner)
    items = wake.peek(spawner.store)
    assert {item.session_id for item in items} == {session_id, twin}, (
        "a row carrying WAKE_ORIGIN and a row the master spawned did not both"
        " reach the wake set"
    )
    assert all(item.bucket in (Bucket.UNFINISHED, Bucket.ERROR) for item in items)
    assert all(item.why for item in items), "a wake item carries no `why`"


def _a_row_that_can_wake(store: Store, tmp_path: Path, spawner: Spawner) -> str:
    """One stopped session whose origin is the one the wake query selects.

    Registered through the store's own verb and classified through M2's own
    lane — the only thing handed in differently from the spawn's row is
    `origin`, which is the column this whole scenario turns on.
    """
    workspace = store.upsert_workspace("twin", str(tmp_path / "twin"))
    row = store.register_session(
        engine_session_id="7c27bb7f-5390-48b0-8b2e-cf4004113d09",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=str(tmp_path / "twin"),
        started_at=NOW,
        origin=Origin(WAKE_ORIGIN),
        ownership=Ownership.OWNED,
    )
    stop_it(store, row.id, tmp_path)
    return row.id


# ----- links 4 and 5: the stamp, and the next turn ----------------------------


def test_the_stamp_moves_once_and_a_second_drain_yields_nothing(
    spawner: Spawner, tmp_path: Path
) -> None:
    """D31's idempotence, driven rather than reasoned about.

    Arrival first: the same reader hands back the row. Then the drain, then the
    second drain — empty, with the stamp asserted to have moved exactly once and
    to be the summary's own `drained_at`.
    """
    twin = _a_row_that_can_wake(spawner.store, tmp_path, spawner)
    assert [item.session_id for item in wake.peek(spawner.store)] == [twin]

    before = spawner.store.get_app_state(wake.MASTER_LAST_TURN_KEY)
    assert before is None, "the stamp was already set before any drain"

    first = wake.drain(spawner.store, lambda: LATER)
    assert [item.session_id for item in first.items] == [twin]
    stamped = spawner.store.get_app_state(wake.MASTER_LAST_TURN_KEY)
    assert stamped == first.drained_at == LATER

    second = wake.drain(spawner.store, lambda: LATER)
    assert second.items == (), "the same row was drained twice"


def test_the_stamp_moves_even_when_the_set_was_empty(spawner: Spawner) -> None:
    """E-M4-18. A stamp conditional on a non-empty drain attributes the next
    stop to a turn that had already ended."""
    assert wake.peek(spawner.store) == ()
    summary = wake.drain(spawner.store, lambda: LATER)
    assert summary.items == ()
    assert spawner.store.get_app_state(wake.MASTER_LAST_TURN_KEY) == LATER


def test_the_next_turn_opens_with_the_wake_summary(
    spawner: Spawner, tmp_path: Path
) -> None:
    """Link 5, through the **only** drain site in `src/`.

    `TurnDriver._opening_text` is what clause 19 makes the single drain (RD-T16-7a
    removed the client's second one), so the summary is read off the prompt the
    runtime was actually handed — never off `render_wake_text` called again by
    the test, which would be a second rendering agreeing with itself.
    """
    twin = _a_row_that_can_wake(spawner.store, tmp_path, spawner)
    masters: list[IdleMaster] = []

    def build(turn_id: str) -> IdleMaster:
        master = IdleMaster()
        masters.append(master)
        return master

    driver = TurnDriver(
        store=spawner.store,
        build_master=build,  # type: ignore[arg-type]
        publish=lambda event: 0,
        withdraw_turn_approvals=lambda turn_id: 0,
        now=lambda: LATER,
    )
    started = driver.send_turn("what happened?")
    assert isinstance(started, TurnStarted), started
    assert driver.wait_for_turn(10.0), "the turn never ended"

    assert masters, "no runtime was built for the turn"
    prompt = masters[0].prompts[0]
    assert wake.WAKE_HEADER in prompt, f"the turn did not open with the summary: {prompt!r}"
    row = spawner.store.get_session(twin)
    assert row is not None
    assert (row.title or twin) in prompt, "the summary names no session"
    assert prompt.endswith("what happened?"), "the user's own text is not beneath it"

    # …and the next turn does not repeat it.
    second = driver.send_turn("and now?")
    assert isinstance(second, TurnStarted), second
    assert driver.wait_for_turn(10.0)
    assert masters[1].prompts[0] == "and now?", "the second turn repeated the wake summary"
    driver.close()


# ----- the seam the repair widened, asserted as a property --------------------


def test_every_registered_handler_is_handed_the_caller(world: World) -> None:
    """D1's repair, at the registry rather than at one tool.

    `invoke()` validated `ctx.audience` and then **discarded the caller** before
    the handler ran, so no handler could know who asked — which is why
    `spawn_session` had one module-level origin and D31's wake set was empty.
    The repair binds `ctx` into the handler call, and that is a property of
    *every* `ToolDef`, not of the one tool that needed it first.

    **Enumerated from the composed registry**, never a list written out here: a
    tool registered tomorrow with a one-argument handler would be a `TypeError`
    inside a call that had already passed the gate and been audited, and a list
    in this file would not have known about it. The composition is the shipped
    `compose_tool_surface`, so the set under test is the product's own.

    Proved by **binding**, not by counting parameters: `Signature.bind` is what
    actually decides whether `tool.handler(args, ctx)` can be called, and a
    handler taking `(*args)` or `(args, ctx, extra=1)` satisfies it for the same
    reason `invoke()` would.
    """
    world.compose()
    tools = registered_tools()
    assert tools, "the composition registered nothing — a scan of nothing finds nothing"

    args: ToolArgs = {}
    ctx = as_master("s2-signature")
    refused: list[str] = []
    for name, tool in sorted(tools.items()):
        try:
            inspect.signature(tool.handler).bind(args, ctx)
        except TypeError as problem:
            refused.append(f"{name}: {problem}")
    assert refused == [], (
        "these handlers cannot be handed the caller, so invoke() would raise"
        f" inside an audited call: {refused}"
    )

    # The control: the same reader on a one-argument handler, which is the shape
    # every handler had before D1 was repaired. Without this the loop above
    # would pass on a `bind` that never refuses anything.
    with pytest.raises(TypeError):
        inspect.signature(lambda only_args: None).bind(args, ctx)
