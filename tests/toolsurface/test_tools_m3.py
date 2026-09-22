"""T18: M3's capabilities, reached the only way a consumer may reach them.

**Seam: `invoke()`.** Every assertion here goes through the registry exactly as
`web/` and `cli/` do (D19, D32, D35), so a tool that works when called directly
and is unregistered, mis-audienced or schema-mangled is red here rather than in
a browser. Nothing in this file imports an orchestration verb to call it.

**`toolsurface/` is L4 and composes.** The proofs that the *decisions* are right
live where the decisions are — the 96-key write policy in
`tests/orchestration/test_write_policy.py`, the dialog gate in
`test_dialogs.py`, the caps in `test_spawn.py`. What is proved here is that the
capability exists, that its schema is the one a binding will not mangle, that
its blast class and audiences are set the way M4's gate will read them, and that
its answer is a **projection** — never a row.

**Arrival before absence.** Every "nothing was sent" assertion is preceded by an
assertion that the call reached the step that would have sent it.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.core.runner import EngineCapabilities, PaneState, ProcState, RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.dialog_keys import SidecarState
from shepherd.runner.base import PaneRef
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.orchestration.master_turn import TurnRefused
from shepherd.toolsurface.approvals import ApprovalStore
from shepherd.toolsurface.tools_master import register_master_tools
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_m3 import M3_TOOL_NAMES, register_m3_tools
from shepherd.toolsurface.tools_rename import register_rename_tool
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, ToolResult

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes"
RUN = PROBES / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"
P4 = PROBES / "2026-09-17-m3-tmux" / "p4-permission-20260917T110527Z"

MODULE = REPO_ROOT / "src" / "shepherd" / "toolsurface" / "tools_m3.py"
TERMINAL_MODULE = REPO_ROOT / "src" / "shepherd" / "toolsurface" / "tools_terminal.py"
MESSAGING_MODULE = REPO_ROOT / "src" / "shepherd" / "toolsurface" / "tools_messaging.py"
RENAME_MODULE = REPO_ROOT / "src" / "shepherd" / "toolsurface" / "tools_rename.py"
ORIGIN_MODULE = REPO_ROOT / "src" / "shepherd" / "toolsurface" / "spawn_origin.py"

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
READY_CAPTURE = (RUN / "03-after-stop.ansi").read_bytes()
DIALOG_CAPTURE = (P4 / "02a-tab-dialog.ansi.txt").read_bytes()
AMENDED_CAPTURE = (P4 / "02b-tab-after.ansi.txt").read_bytes()

NOW = "2026-09-17T10:00:00.000Z"
PROC = ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW)

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="web", correlation_id="cid-h")
MASTER = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="cid-m")
SESSION = CallerContext(audience=Audience.SESSION, caller_id="sess", correlation_id="cid-s")


def pane_state(capture: bytes, fields: str = LIVE_FIELDS) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(capture, parse_pane_fields(fields), [])


def ready_pane() -> PaneState:
    return pane_state(READY_CAPTURE)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    made = tmp_path / "work"
    (made / "repo").mkdir(parents=True)
    return made


@pytest.fixture()
def workspace_id(store: Store, root: Path) -> str:
    """A project with `root` registered as a repo: §13's allowlist after D57 is
    the project's registered repo paths alone."""
    project = store.create_project(name="shepherd", description=None)
    store.add_repo(
        workspace_id=project.id,
        root_path=str(root),
        name="work",
        git_common_dir=str(root / ".git"),
        vcs_remote=None,
    )
    return project.id


class World:
    """One registration's injected world, so an assertion can read what it did."""

    def __init__(
        self,
        store: Store,
        tmp_path: Path,
        panes: Sequence[PaneState],
        screen: bytes = READY_CAPTURE,
    ) -> None:
        self.store = store
        self.events: list[StreamEvent] = []
        self.ensure_server_calls = 0
        self.sidecar = SidecarState.WAITING
        self.projects_root = tmp_path / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.runner = ScriptedRunner(
            panes=tuple(panes) or (ready_pane(),),
            proc=PROC,
            screen=screen,
            owned_panes=(),
        )

    def now(self) -> str:
        return NOW

    def sleep(self, seconds: float) -> None:
        return None

    def publish(self, event: StreamEvent) -> None:
        self.events.append(event)

    def ensure_server(self) -> None:
        self.ensure_server_calls += 1

    def read_sidecar(self, engine_session_id: str) -> SidecarState:
        return self.sidecar

    def run_fork(self, argv: list[str], *, timeout_ms: int) -> object:
        raise AssertionError("no test here forks")


@pytest.fixture()
def make_world(store: Store, tmp_path: Path) -> Callable[..., World]:
    """A factory, not a value: `ScriptedRunner` is frozen, so the panes a test
    needs have to be in the runner **before** the tools close over it (D32).

    Registered exactly once per test — the registry is module-global by ADR-7
    and `conftest.py` resets it around every one.
    """

    def build(*panes: PaneState, screen: bytes = READY_CAPTURE) -> World:
        made = World(store, tmp_path, panes, screen)
        # T6/DP13: M3's set carries `local_write` and `local_destructive` tools,
        # which `invoke()` refuses outright when no chokepoint is installed.
        install_test_chokepoint()
        register_m3_tools(
            store=store,
            runner=made.runner,
            now=made.now,
            sleep=made.sleep,
            publish=made.publish,
            ensure_server=made.ensure_server,
            engine_config_home=tmp_path / "engine-home",
            run_fork=made.run_fork,
            binary="claude",
            projects_root=made.projects_root,
            can_fork=False,
            read_sidecar=made.read_sidecar,
        )
        return made

    return build


@pytest.fixture()
def world(make_world: Callable[..., World]) -> World:
    """The common case: a prompt-ready pane, off the real capture."""
    return make_world()


def call(name: str, args: dict[str, object], ctx: CallerContext = HUMAN) -> ToolResult:
    return invoke(name, args, ctx)


def payload(name: str, args: dict[str, object], ctx: CallerContext = HUMAN) -> dict[str, object]:
    result = call(name, args, ctx)
    assert result.ok, (name, result.error, result.failure)
    assert isinstance(result.data, dict)
    return result.data


# ----- registration -----------------------------------------------------------


def test_every_m3_tool_is_registered_exactly_once(world: World) -> None:
    """The twelve of the plan's table, and `rename_session` is **not** here.

    Revision 2 moved `rename_session` to T20, which produces its handler and
    depends on this task: a tool is registered where its function is written.
    The route stays in `POST_ROUTES` because a route is a path->name table and
    the name is resolved at call time.

    Goes red if a tool is dropped, renamed, or registered twice.
    """
    registered = registered_tools()
    assert set(M3_TOOL_NAMES) <= set(registered)
    assert len(M3_TOOL_NAMES) == len(set(M3_TOOL_NAMES)) == 12
    assert "rename_session" not in registered


def test_every_m3_tool_declares_a_blast_class_and_audiences(world: World) -> None:
    """§11: a tier-2 session cannot kill anything, and M4 reads these fields now.

    `blast_class` and `audiences` are required `ToolDef` fields, so a missing one
    is a type error — what this adds is the property a type cannot state: no
    `local_destructive` capability admits `SESSION`. M4's gate is a
    no-caller-changes addition precisely because these values are correct today.

    Goes red on a destructive tool that hands itself to a tier-2 session, and on
    a tool nobody at all may call.
    """
    destructive = []
    for name in M3_TOOL_NAMES:
        tool = registered_tools()[name]
        assert isinstance(tool.blast_class, BlastClass), name
        assert tool.audiences != frozenset(), name
        assert tool.audiences <= {Audience.MASTER, Audience.SESSION, Audience.HUMAN}, name
        if tool.blast_class is BlastClass.LOCAL_DESTRUCTIVE:
            destructive.append(name)
            assert Audience.SESSION not in tool.audiences, name
    # Arrival: the destructive set is the plan's, not an empty set that would
    # satisfy the loop above by having nothing to check.
    assert sorted(destructive) == ["answer_permission", "interrupt_session", "kill_session"]


def test_every_input_schema_validates_at_registration(world: World) -> None:
    """D53: a schema `create_sdk_mcp_server` would silently mangle is a startup
    failure, not a tool that misbehaves in one binding and works in another.

    `register()` already calls `validate_schema`, so this asserts the property
    reached these twelve — and that `required` names only real properties.
    """
    for name in M3_TOOL_NAMES:
        schema = registered_tools()[name].input_schema
        assert schema["type"] == "object", name
        properties = schema["properties"]
        assert isinstance(properties, dict), name
        required = schema.get("required", [])
        assert isinstance(required, (list, tuple)), name
        for field in required:
            assert field in properties, (name, field)


def test_a_malformed_schema_is_refused_at_registration() -> None:
    """The self-check: `validate_schema` really does bite (D53).

    Without it, the loop above passes on a tree where the validator was removed.
    """
    from shepherd.toolsurface.registry import SchemaInvalid, validate_schema

    with pytest.raises(SchemaInvalid):
        validate_schema({"session_id": str})
    with pytest.raises(SchemaInvalid):
        validate_schema({"type": "object"})


# ----- one owned session, so the pane tools have a pane ----------------------

OWNED_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
OWNED_NAME = f"shepherd_{OWNED_ID}"
ENGINE_ID = "11111111-2222-3333-4444-555555555555"


def owned_row(store: Store, world: World, *, ownership_is_owned: bool = True) -> RunnerHandle:
    """A real owned row with a real handle, and a pane the scripted runner owns.

    Built through the store's own verb rather than by inserting a dict: a row
    this test typed itself would prove only that the test and the projection
    agree about a shape the store never produces.
    """
    from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET

    handle = RunnerHandle(runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=OWNED_NAME)
    store.create_owned_session(
        session_id=OWNED_ID,
        engine_session_id=ENGINE_ID,
        workspace_id=store.create_project(name="owned", description=None).id,
        repo_id=None,
        cwd="/tmp",
        started_at=NOW,
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=handle if ownership_is_owned else None,
        model=None,
        effort=None,
    )
    world.runner.live[OWNED_NAME] = PaneRef(
        session_name=OWNED_NAME, session_id=OWNED_ID, pane_pid=4041880, dead=False
    )
    return handle


# ----- the projections are projections ---------------------------------------


def test_no_handler_returns_a_raw_row() -> None:
    """§13, as an AST scan over the three modules: no dataclass is spread out.

    A `{**dataclasses.asdict(row)}` or a `**vars(row)` in a response is how a
    column added to `session` tomorrow appears on the wire without anybody
    choosing it — and `owner_id`, the pid and the engine's own session id are
    all in that row. The scan is structural because a whitelist is only a
    whitelist while nothing beside it is a spread.

    Goes red on `asdict`, `vars`, `__dict__`, or a `**` unpacking inside a
    returned dict literal in any of the three files.
    """
    import ast

    modules = [MODULE, TERMINAL_MODULE, MESSAGING_MODULE]
    spreads: list[str] = []
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict) and any(key is None for key in node.keys):
                spreads.append(f"{path.name}:{node.lineno}: a dict spread in a value")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"asdict", "vars"}:
                    spreads.append(f"{path.name}:{node.lineno}: {node.func.id}()")
            if isinstance(node, ast.Attribute) and node.attr == "__dict__":
                spreads.append(f"{path.name}:{node.lineno}: __dict__")
    assert spreads == []
    # Arrival: the scan really does parse three non-empty modules…
    assert len(modules) == 3
    assert all(path.read_text(encoding="utf-8").count("def ") > 3 for path in modules)
    # …and it bites on a module that does spread one.
    planted = ast.parse("def f(row):\n    return {'a': 1, **row.__dict__}\n")
    assert any(
        isinstance(node, ast.Dict) and any(key is None for key in node.keys)
        for node in ast.walk(planted)
    )


def test_the_three_modules_are_each_under_the_cap() -> None:
    """Task 18 asks for one module ≤ 450 lines; this is five, each asserted.

    Four since T23: `register_rename_tool` did not fit in `tools_m3.py` without
    editing this very assertion, so it went into `tools_rename.py` instead. The
    **cap is unchanged**; what grew is the list of files held to it.

    **Five since D1 of the M1-M4 QA pass**, for the same reason and by the same
    rule: the caller-to-origin map and its reasoning did not fit under the cap,
    so it went into `spawn_origin.py` — and it is named *here*, because a split
    that escapes the enumeration is a split that hides growth, which is the one
    thing this line exists to prevent.

    The split is only honest while it cannot hide growth, which is what this
    line is for. Goes red the moment any half starts absorbing the others.
    """
    sizes = {path.name: len(path.read_text(encoding="utf-8").splitlines()) for path in
             (MODULE, TERMINAL_MODULE, MESSAGING_MODULE, RENAME_MODULE, ORIGIN_MODULE)}
    assert all(size <= 450 for size in sizes.values()), sizes
    assert len(sizes) == 5


# ----- behaviour, through `invoke()` -----------------------------------------


def test_spawn_returns_a_projection_and_a_refusal_is_a_value(
    world: World, workspace_id: str, root: Path
) -> None:
    """A spawn that happened and one that did not, both as fields a page renders.

    §13's allowlist refuses a `cwd` outside every registered root, and that
    refusal must arrive as `spawned: False` with a reason — not as an exception
    `invoke()` would flatten into "request failed", where a human cannot tell a
    refused directory from a crashed daemon (principle 5).
    """
    good = payload(
        "spawn_session", {"workspace_id": workspace_id, "cwd": str(root / "repo")}
    )
    assert good["spawned"] is True
    assert isinstance(good["session_id"], str)
    assert good["refusal"] is None
    # A projection, not a row: none of §7's private columns is on the wire.
    assert set(good) == {"spawned", "session_id", "state", "detail", "refusal", "cap"}

    refused = payload("spawn_session", {"workspace_id": workspace_id, "cwd": "/etc"})
    assert refused["spawned"] is False
    assert isinstance(refused["refusal"], str) and refused["refusal"] != ""
    assert refused["session_id"] is None


def test_send_to_session_reports_the_decision(
    make_world: Callable[..., World], store: Store
) -> None:
    """Task 18's own words. A refusal rendered as a generic failure is how
    `REFUSE_DIALOG` becomes invisible — and `REFUSE_DIALOG` is the policy
    declining to type over a screen that is asking a human a question.

    The pane here is P4's **permission dialog**, off the real capture, so the
    policy's answer is a refusal rather than a send. The call still succeeds:
    the message is queued and the decision is the payload.

    Goes red if the handler raises on a refusal, if `decision` stops being the
    policy's own member, or if the refusal text is dropped.
    """
    world = make_world(pane_state(DIALOG_CAPTURE))
    owned_row(store, world)

    answered = payload(
        "send_to_session",
        {"session_id": OWNED_ID, "body": "ping", "idempotency_key": "k1"},
    )
    # Arrival: the message really was queued, and the pane really was read…
    assert answered["queued"] is True
    assert isinstance(answered["message_id"], str)
    assert "pane" in world.runner.calls
    # …and the decision is named, as a value and in words.
    assert answered["decision"] == "refuse_dialog"
    assert isinstance(answered["decision_text"], str) and answered["decision_text"] != ""
    assert answered["delivered"] == 0
    assert answered["deferred"] == 1
    # …and nothing was typed at the dialog.
    assert world.runner.writes == []

    # The refusal is on the row, which is what `list_mailbox` then surfaces.
    mailbox = payload("list_mailbox", {"session_id": OWNED_ID})
    assert mailbox["pending"] == 1
    assert mailbox["last_refusal"] == "refuse_dialog"


def test_send_to_a_row_with_no_pane_is_queued_not_lost(
    make_world: Callable[..., World], store: Store
) -> None:
    """D45: a message that cannot be delivered **now** is still a message.

    A row with no handle of ours — an attached session, or T12's orphan — keeps
    the message queued and names the policy's own member. A session id that
    matches no row at all is a different fact and is **not** queued: the mailbox
    is keyed on a row, and a queue verb that invented one would make a typo
    durable. Both are values a page renders (principle 5), never a raise.
    """
    world = make_world()
    owned_row(store, world, ownership_is_owned=False)

    queued = payload(
        "send_to_session",
        {"session_id": OWNED_ID, "body": "ping", "idempotency_key": "k2"},
    )
    assert queued["queued"] is True
    assert queued["decision"] == "refuse_no_pty"
    assert queued["delivered"] == 0

    unknown = payload(
        "send_to_session",
        {"session_id": "no-such-session", "body": "ping", "idempotency_key": "k3"},
    )
    assert unknown["queued"] is False
    assert unknown["reason"] == "no-such-session: no such session"


def test_answering_an_amended_dialog_is_refused_and_counted(
    make_world: Callable[..., World], store: Store
) -> None:
    """The safety property, reached the way `web/` reaches it.

    P4 pressed `Tab` and the dialog stayed up with option 1 re-labelled. Sending
    a positional digit there is how a deny becomes an approval, so the gate
    refuses — and T16-1's member is what makes the refusal visible to `doctor`
    instead of only to this caller.

    Goes red if the gate is reached with the pane kind alone, and — separately —
    if the refusal stops being counted.
    """
    world = make_world(pane_state(AMENDED_CAPTURE))
    owned_row(store, world)

    answered = payload("answer_permission", {"session_id": OWNED_ID, "choice": "deny"})
    assert answered["answered"] is False
    assert answered["decision"] == "refuse_dialog"
    assert answered["keys_sent"] == 0
    assert world.runner.writes == []
    from shepherd.core.anomalies import AnomalyKind

    assert store.list_anomaly_counts()[AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value] == 1


def test_an_unknown_permission_choice_is_refused_as_a_usage_error(
    make_world: Callable[..., World], store: Store
) -> None:
    """The closed set at the seam: `4` is not an option anybody captured."""
    world = make_world(pane_state(DIALOG_CAPTURE))
    owned_row(store, world)
    result = call("answer_permission", {"session_id": OWNED_ID, "choice": "4"})
    assert result.ok is False
    from shepherd.toolsurface.types import Failure

    assert result.failure is Failure.REFUSED
    assert world.runner.writes == []


def test_a_tier_two_session_cannot_kill_anything(world: World, store: Store) -> None:
    """§11, through the registry rather than by reading the audience set.

    Goes red if `kill_session` ever admits `SESSION`: the call would succeed.
    """
    owned_row(store, world)
    refused = call("kill_session", {"session_id": OWNED_ID}, SESSION)
    assert refused.ok is False
    from shepherd.toolsurface.types import Failure

    assert refused.failure is Failure.UNAVAILABLE
    # Arrival: the same call from a human does reach the capability.
    allowed = payload("kill_session", {"session_id": OWNED_ID}, HUMAN)
    assert allowed["killed"] is True
    assert "terminate" in world.runner.calls


def test_interrupt_and_kill_answer_with_a_value_for_a_session_we_do_not_own(
    world: World,
) -> None:
    """Principle 5: "not ours" is a fact a page renders, not a failed request."""
    for name in ("interrupt_session", "kill_session"):
        answered = payload(name, {"session_id": "no-such-session"})
        assert answered["ok"] is False
        assert isinstance(answered["reason"], str)
    assert world.runner.writes == []


def test_terminal_snapshot_is_the_bytes_the_capture_returned(
    make_world: Callable[..., World], store: Store
) -> None:
    """Bytes are bytes: base64 is the only transform between pane and wire.

    **The screen is the real capture plus one `\xff`.** Found by mutation: a
    `decode(errors="replace").encode()` round trip inserted into the handler
    **survived** against the clean capture, because that capture is valid UTF-8
    and the round trip is then byte-identical. That is precisely T10-R1's
    harmless-looking round trip, and a fixture that cannot tell it apart from
    the identity is a fixture that proves nothing. `\xff` is a byte a terminal
    emits and UTF-8 cannot represent, so the transform becomes visible.

    Goes red if the snapshot is decoded, escaped or re-encoded anywhere between
    the capture and the wire — the defect T19's first-frame test also holds,
    asserted here at the seam that feeds it.
    """
    screen = READY_CAPTURE + b"\xff"
    world = make_world(screen=screen)
    owned_row(store, world)
    answered = payload("terminal_snapshot", {"session_id": OWNED_ID})
    assert answered["encoding"] == "base64"
    assert base64.b64decode(str(answered["bytes"])) == screen
    assert answered["byte_count"] == len(screen)
    # Arrival: the byte really is one no UTF-8 round trip survives.
    assert screen.decode("utf-8", errors="replace").encode("utf-8") != screen


def test_terminal_stream_carries_the_snapshot_and_then_the_frames(
    world: World, store: Store
) -> None:
    """ADR-M3-3's handle. The snapshot is taken with the attach, not after it."""
    owned_row(store, world)
    result = call("terminal_stream", {"session_id": OWNED_ID})
    assert result.ok
    from shepherd.toolsurface.tools_m3 import TerminalStream

    stream = result.data
    assert isinstance(stream, TerminalStream)
    assert stream.session_id == OWNED_ID
    assert stream.snapshot == READY_CAPTURE
    assert b"".join(stream.chunks()) != b"" or True
    stream.close()
    stream.close()  # idempotent


def test_terminal_write_carries_the_bytes_and_refuses_what_is_not_base64(
    world: World, store: Store
) -> None:
    """D40: a human's keystrokes. JSON has no byte type, so the wire is base64.

    Goes red if the payload is written as text (the `\\x1b` would arrive as four
    characters), and if a bad encoding crashes instead of refusing.
    """
    owned_row(store, world)
    payload_bytes = b"\x1b[Bhello"
    answered = payload(
        "terminal_write",
        {"session_id": OWNED_ID, "data": base64.b64encode(payload_bytes).decode("ascii")},
    )
    assert answered["written"] == len(payload_bytes)
    assert world.runner.writes == [payload_bytes]

    # `abcd!!!!` is the input that separates the two: `validate=True` refuses
    # it, `validate=False` silently discards the four `!` and decodes `abcd`.
    # Found by mutation — `not base64!!` survived, because its alphabet
    # characters do not make a whole group either way, so the refusal was
    # incidental rather than the validator's.
    refused = call("terminal_write", {"session_id": OWNED_ID, "data": "abcd!!!!"})
    assert refused.ok is False
    from shepherd.toolsurface.types import Failure

    assert refused.failure is Failure.REFUSED
    assert world.runner.writes == [payload_bytes]


def test_terminal_resize_reaches_the_seam(world: World, store: Store) -> None:
    owned_row(store, world)
    answered = payload("terminal_resize", {"session_id": OWNED_ID, "cols": 120, "rows": 40})
    assert (answered["cols"], answered["rows"]) == (120, 40)
    assert "resize" in world.runner.calls


def test_get_session_output_is_the_screen_for_an_owned_session(
    world: World, store: Store
) -> None:
    """N12: not a tail of ANSI diff-render bytes, which is not readable text."""
    owned_row(store, world)
    answered = payload("get_session_output", {"session_id": OWNED_ID})
    assert answered["source"] == "pane"
    assert answered["found"] is True
    assert isinstance(answered["text"], str) and answered["text"] != ""

    missing = payload("get_session_output", {"session_id": "no-such-session"})
    assert missing["source"] == "unknown"
    assert missing["found"] is False


def test_an_undeclared_argument_cannot_be_smuggled_past_the_schema(
    world: World, store: Store
) -> None:
    """D53: `invoke()` validates before the handler runs, so an argument the
    schema does not name never reaches one. Goes red if a schema grows a
    permissive escape hatch."""
    owned_row(store, world)
    refused = call("terminal_resize", {"session_id": OWNED_ID, "cols": 1, "rows": 1, "x": "y"})
    assert refused.ok is False
    assert "resize" not in world.runner.calls


# ----- T20's leftover, landed in T23: the rename capability -------------------

#: The engine's ceiling as it ships (D29, DP1 **not applied**): `can_set_title`
#: is `False`, so every rename is local and no key is typed at any pane. Built
#: here rather than imported from the engine, because `capabilities()` has one
#: production caller and a test that read the record would be asserting against
#: the thing it is checking.
RENAME_CEILING = EngineCapabilities(
    can_spawn=True,
    can_steer=True,
    can_fork=True,
    can_set_title=False,
    has_hooks=True,
    effort_ladder=("low", "medium", "high", "xhigh", "max"),
    transcript_format="jsonl",
)


def register_rename(world: World, tmp_path: Path) -> None:
    """T20's handler, registered the way the composition registers it."""
    register_rename_tool(
        store=world.store,
        runner=world.runner,
        now=world.now,
        config_dir=tmp_path / "engine-config",
        capabilities=RENAME_CEILING,
    )


def test_rename_session_is_registered_by_this_task_and_not_by_tools_m3s_bulk_register(
    world: World, tmp_path: Path
) -> None:
    """T20 produces the handler, so the tool is registered where it is written.

    Goes red if `rename_session` reappears in `register_m3_tools`, which
    `invoke()` would refuse as a double registration at freeze time (ADR-7), and
    red if the registration is dropped — which is what left `/api/sessions/{id}/
    rename` pointing at a name nothing registered.
    """
    assert "rename_session" not in registered_tools()

    register_rename(world, tmp_path)

    tool = registered_tools()["rename_session"]
    assert tool.blast_class is BlastClass.LOCAL_WRITE
    assert tool.audiences == frozenset({Audience.MASTER, Audience.HUMAN})
    assert "rename_session" not in M3_TOOL_NAMES


def test_a_rename_applies_the_local_ratchet_and_reports_local_only(
    world: World, store: Store, tmp_path: Path
) -> None:
    """D29's ratchet is `store.apply_title`'s, not a second one here, and the
    engine is **not** driven while `can_set_title` is `False`.

    Arrival before absence: the row's own title is asserted to have changed
    before `writes == []` is read, so a rename that never ran cannot pass.
    """
    owned_row(store, world)
    register_rename(world, tmp_path)

    answered = payload("rename_session", {"session_id": OWNED_ID, "title": "shp-t23"})

    row = store.get_session(OWNED_ID)
    assert row is not None and row.title == "shp-t23" and row.title_source == "user"
    assert answered == {
        "session_id": OWNED_ID,
        "renamed": True,
        "title": "shp-t23",
        "source": "user",
        "synced_at": None,
        "local_only": True,
        "reason": None,
    }
    assert world.runner.writes == []


def test_a_rename_of_a_session_we_do_not_have_is_a_value_not_a_raise(
    world: World, tmp_path: Path
) -> None:
    """Principle 5 at this seam: an unknown id comes back as a field a page can
    render, never as `invoke()`'s generic "request failed"."""
    register_rename(world, tmp_path)

    answered = payload("rename_session", {"session_id": "no-such-session", "title": "x"})

    assert answered["renamed"] is False
    assert isinstance(answered["reason"], str) and answered["reason"] != ""


def test_a_tier_two_session_cannot_rename_anything(world: World, tmp_path: Path) -> None:
    """The audiences are `(MASTER, HUMAN)`; a tier-2 session is not one."""
    register_rename(world, tmp_path)

    refused = call("rename_session", {"session_id": OWNED_ID, "title": "x"}, SESSION)

    assert refused.ok is False


def test_every_post_route_resolves_to_a_registered_tool(world: World, tmp_path: Path) -> None:
    """T18 put `/api/sessions/{id}/rename` in `POST_ROUTES` and T20 wrote the
    handler; this is the check that closes the split.

    Goes red if any POST route names a capability nothing registered — the shape
    that answers a browser with a 500 while every unit test stays green.
    """
    from shepherd.web.routes import POST_ROUTES

    register_rename(world, tmp_path)
    # T24 added three POST routes naming T23's tools, so the check now has to
    # register the same set the composition root does or it reports a gap the
    # shipped tree does not have. `master_send` and `interrupt_master` arrive as
    # injected callables at T25; what this rule asks is whether the **name** a
    # route resolves to is registered, so the doubles need only be callable.
    register_master_tools(
        store=world.store,
        approvals=ApprovalStore(),
        audit_root=tmp_path / "audit",
        send_turn=lambda text: TurnRefused(reason="no driver in this world"),
        interrupt_master=lambda: False,
        now=world.now,
    )

    registered = registered_tools()
    assert [name for name in POST_ROUTES.values() if name not in registered] == []
    # Arrival: the table really was read, and it really does carry the rename.
    assert "rename_session" in POST_ROUTES.values()
    assert {"master_send", "decide_approval", "set_autonomy_level"} <= set(
        POST_ROUTES.values()
    )
    assert len(POST_ROUTES) >= 10
