"""T11: the spawn sequence — the row before the process, the caps, the dialog.

**The two proofs this file exists for, and what makes each of them real:**

1. **C-M3-7 — the row exists before the process does.** Asserted by making
   `runner.start` raise and then finding the row: an ordering claim proved by an
   *observation after a failure*, not by reading the source. Swapping steps 4 and
   5 turns it red.
2. **Clause 3 / P-M3-6 — a spawn into an untrusted directory never answers the
   dialog.** Driven through **`LocalRunner` with a counting `run_argv`**, because
   `ScriptedRunner` has no `run_argv` at all: a stray `Enter` sent through
   `interrupt` (`send-keys Escape`) or any of the other nine members would leave
   `ScriptedRunner.writes == []` and a `writes`-only assertion green. The
   `ScriptedRunner` row is kept beside it as the fast path, never as the proof.

   **Arrival, then absence.** Every zero-count assertion in this file is preceded
   by an assertion that the spawn *reached* the step that would have sent the
   key — the state is `needs_you` and the directory is named — because "no keys
   were sent" passes just as well when nothing ever ran. That is this repo's
   dominant defect class and the reason clause 3 words the order.

**Captures, not hand-written screens.** Every `PaneState` here comes out of the
shipped classifier (`runner.pane.read_pane`) over a real `capture-pane -e -p`
capture named in `data-schemas.md`. A screen this file typed itself would prove
only that the test and the classifier agree.
"""

from __future__ import annotations

import dataclasses
import typing
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.runner import (
    MAX_CHILDREN_PER_SESSION,
    MAX_SESSION_DEPTH,
    MAX_TOTAL_OWNED_SESSIONS,
    PaneKind,
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
)
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.spawn import spawn_argv as engine_spawn_argv
from shepherd.host.base import DetachedLaunch
from shepherd.orchestration.spawn import (
    CAP_CHILDREN,
    CAP_DEPTH,
    CAP_TOTAL,
    POLL_OUTCOME,
    SPAWN_EVENT,
    SpawnOutcome,
    SpawnRefused,
    spawn_owned_session,
)
from shepherd.runner.base import PaneRef
from shepherd.runner.local import CommandResult, LocalRunner
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = (
    REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"
)
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "spawn.py"
ADMISSION = REPO_ROOT / "src" / "shepherd" / "orchestration" / "admission.py"

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
#: `01-trust-dialog-fmt.txt`: the trust screen is **not** on the alternate screen.
TRUST_FIELDS = "0|0||✳ Claude Code|160|45|4041880"
#: `14-list-sessions-after-sigterm.txt`, `probe_sig`: dead, status 143.
DEAD_FIELDS = "0|1|143||160|45|4042531"

TRUST_CAPTURE = (RUN / "01-trust-dialog.ansi").read_bytes()
READY_CAPTURE = (RUN / "03-after-stop.ansi").read_bytes()

TMUX = "tmux"
SOCKET = "shepherd-m3-t11"
NOW = "2026-09-17T10:00:00.000Z"

#: Every tmux verb or argument that can put a byte into a pane. A **set**, not
#: the one verb a mock would expect: a bare `Enter` selects "No, exit" (A11) and
#: it can arrive through `send-keys`, through `paste-buffer`, or as the literal
#: word appended to some other argv.
KEY_DELIVERING = ("send-keys", "paste-buffer", "Enter", "C-m", "KPEnter")


# ----- fixtures ---------------------------------------------------------------


def pane_state(capture: bytes, fields: str) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(capture, parse_pane_fields(fields), [])


def trust_pane() -> PaneState:
    return pane_state(TRUST_CAPTURE, TRUST_FIELDS)


def ready_pane() -> PaneState:
    return pane_state(READY_CAPTURE, LIVE_FIELDS)


def dead_pane() -> PaneState:
    return pane_state(b"", DEAD_FIELDS)


def unreadable_pane() -> PaneState:
    """Bytes that are not a screen: the kind that decides nothing (principle 5)."""
    return pane_state(b"\xff\xfe not utf-8", LIVE_FIELDS)


PROC = ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """A registered workspace root that really exists, so `resolve()` is real."""
    made = tmp_path / "work"
    (made / "repo").mkdir(parents=True)
    return made


@pytest.fixture()
def workspace_id(store: Store, root: Path) -> str:
    """A project with `root` registered as a repo — §13's allowlist after D57 is
    the registered repo paths alone, so the fixture registers one."""
    project = store.create_project(name="shepherd", description=None)
    store.add_repo(
        workspace_id=project.id,
        root_path=str(root),
        name="work",
        git_common_dir=str(root / ".git"),
        vcs_remote=None,
    )
    return project.id


class Clock:
    """An injected clock that advances only when the sequence sleeps.

    The poll's deadline is arithmetic over `now()`, so a clock the *test* drives
    is what makes a 60-second timeout a 6-call test. It is never a wall clock.
    """

    def __init__(self, step_s: float = 0.25) -> None:
        self.millis = 0
        self.step_s = step_s

    def __call__(self) -> str:
        whole, fraction = divmod(self.millis, 1000)
        minutes, seconds = divmod(whole, 60)
        return f"2026-09-17T10:{minutes:02d}:{seconds:02d}.{fraction:03d}Z"

    def sleep(self, seconds: float) -> None:
        self.millis += int(seconds * 1000)


@dataclasses.dataclass
class Spawned:
    """One call's injected world, so an assertion can read what it did."""

    events: list[StreamEvent] = dataclasses.field(default_factory=list)
    ensure_server_calls: int = 0
    clock: Clock = dataclasses.field(default_factory=Clock)
    ensure_server_refusal: str | None = None

    def ensure_server(self) -> None:
        self.ensure_server_calls += 1
        if self.ensure_server_refusal is not None:
            raise RunnerRefusal(self.ensure_server_refusal)


def scripted(
    panes: Sequence[PaneState] = (),
    owned: Sequence[PaneRef] = (),
) -> ScriptedRunner:
    return ScriptedRunner(
        panes=tuple(panes), proc=PROC, screen=READY_CAPTURE, owned_panes=tuple(owned)
    )


def owned_panes(count: int) -> tuple[PaneRef, ...]:
    """`count` live panes with real `shepherd_<ULID>` names."""
    base = "01JBQ8Z9XKME5RT3VWNY6P0D"
    return tuple(
        PaneRef(
            session_name=f"shepherd_{base}{index:02d}",
            session_id=f"{base}{index:02d}",
            pane_pid=4041880 + index,
            dead=False,
        )
        for index in range(count)
    )


def spawn(
    *,
    store: Store,
    runner: object,
    workspace_id: str,
    cwd: str,
    world: Spawned | None = None,
    engine_config_home: Path | None = None,
    parent_session_id: str | None = None,
    brief: str | None = "ship it",
    title: str | None = None,
    origin: Origin = Origin.ORCHESTRATOR,
) -> tuple[SpawnOutcome | SpawnRefused, Spawned]:
    here = world if world is not None else Spawned()
    result = spawn_owned_session(
        store=store,
        runner=typing.cast(typing.Any, runner),  # noqa: ANN401 - the Runner seam, structurally
        now=here.clock,
        sleep=here.clock.sleep,
        publish=here.events.append,
        ensure_server=here.ensure_server,
        engine_config_home=engine_config_home,
        workspace_id=workspace_id,
        cwd=cwd,
        brief=brief,
        title=title,
        model=None,
        effort=None,
        parent_session_id=parent_session_id,
        origin=origin,
    )
    return result, here


def trusted_home(tmp_path: Path, cwd: str, trusted: bool) -> Path:
    """A throwaway engine config home. **Never** the user's real one (T10-R1)."""
    home = tmp_path / "engine-home"
    home.mkdir(exist_ok=True)
    (home / ".claude.json").write_text(
        '{"projects": {"%s": {"hasTrustDialogAccepted": %s}}}'
        % (cwd, "true" if trusted else "false"),
        encoding="utf-8",
    )
    return home


# ----- 1 · the row exists before the process does (C-M3-7) --------------------


class ExplodingRunner:
    """A runner whose `start` raises, and which records what it was asked."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self, spec: SessionSpec) -> RunnerHandle:
        self.calls.append("start")
        raise RunnerRefusal("the pane could not be created")

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        self.calls.append("list_owned_panes")
        return ()

    def pane(self, handle: RunnerHandle) -> PaneState:  # pragma: no cover - never reached
        raise AssertionError("the poll must not run after start failed")


def test_the_row_exists_before_the_process_does(
    store: Store, workspace_id: str, root: Path
) -> None:
    """C-M3-7, asserted by observation after a failure rather than by reading code.

    Goes red if steps 4 and 5 are swapped: with `start` before
    `create_owned_session`, the refusal leaves no row at all and the engine id is
    bound to nothing.
    """
    runner = ExplodingRunner()
    result, _ = spawn(
        store=store, runner=runner, workspace_id=workspace_id, cwd=str(root / "repo")
    )

    assert runner.calls == ["list_owned_panes", "start"], runner.calls
    assert isinstance(result, SpawnRefused), result
    rows = store.list_sessions(workspace_id=workspace_id)
    assert len(rows) == 1, "the row must survive a failed start — it is what T12 reconciles"
    assert rows[0].ownership is Ownership.OWNED
    assert rows[0].engine_session_id is not None, "a spawn row is engine-bound from birth"
    assert rows[0].runner_handle is None, "no handle: the pane never came up"


# ----- 2 · clause 3 / P-M3-6 · no key is ever sent ----------------------------


class CountingTmux:
    """A counting `run_argv`: every argv, answered the way tmux answers.

    Not a mock with expectations — it **records**, so a test can assert the spawn
    reached its pane read *before* it asserts that nothing was sent.
    """

    def __init__(self, capture: bytes, fields: str) -> None:
        self.calls: list[list[str]] = []
        self.capture = capture
        self.fields = fields
        self.rows: dict[str, str] = {}

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        words = argv[argv.index(SOCKET) + 1 :] if SOCKET in argv else argv[1:]
        verb = words[0] if words else ""
        if verb == "new-session":
            self.rows[words[words.index("-s") + 1]] = self.fields
            return CommandResult(rc=0, stdout=b"", stderr=b"")
        if verb == "list-sessions":
            if not self.rows:
                return CommandResult(rc=1, stdout=b"", stderr=b"no server running")
            listing = "".join(f"{name}|{tail}\n" for name, tail in sorted(self.rows.items()))
            return CommandResult(rc=0, stdout=listing.encode("utf-8"), stderr=b"")
        if verb == "capture-pane":
            return CommandResult(rc=0, stdout=self.capture, stderr=b"")
        return CommandResult(rc=0, stdout=b"", stderr=b"")

    def key_argvs(self) -> list[list[str]]:
        return [
            argv
            for argv in self.calls
            if any(word in KEY_DELIVERING for word in argv)
        ]


def local_runner(counter: CountingTmux, anomalies: list[Anomaly]) -> LocalRunner:
    """The real driver, with only its one command seam replaced."""
    return LocalRunner(
        socket=SOCKET,
        run_argv=counter,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: NOW,
        spawn_argv=lambda spec, *, frame_bytes: engine_spawn_argv(
            spec, "/usr/bin/claude", frame_bytes=frame_bytes
        ),
        record_anomaly=anomalies.append,
        sink_dir=Path("/tmp/shepherd-t11"),
    )


def test_an_untrusted_directory_becomes_needs_you_and_no_key_is_sent(
    store: Store, workspace_id: str, root: Path, tmp_path: Path
) -> None:
    """Clause 3 / P-M3-6, through `LocalRunner` and its counting `run_argv`.

    **Arrival first.** A spawn that returned before step 6 would send zero keys
    too, so the state, the reason and the recorded pane read are asserted before
    the count. Only then: no argv in the whole run carries a key.
    """
    cwd = str(root / "repo")
    counter = CountingTmux(TRUST_CAPTURE, TRUST_FIELDS)
    anomalies: list[Anomaly] = []
    result, world = spawn(
        store=store,
        runner=local_runner(counter, anomalies),
        workspace_id=workspace_id,
        cwd=cwd,
        engine_config_home=trusted_home(tmp_path, cwd, trusted=False),
    )

    # --- arrival: the spawn really ran, and really read the pane -------------
    assert isinstance(result, SpawnOutcome), result
    assert result.state is SessionState.NEEDS_YOU
    assert cwd in result.detail, result.detail
    assert "workspace trust" in result.detail, result.detail
    verbs = [argv[argv.index(SOCKET) + 1] for argv in counter.calls if SOCKET in argv]
    assert "new-session" in verbs, verbs
    assert "capture-pane" in verbs, "the spawn never reached step 6's pane read"
    row = store.get_owned_session(result.session_id)
    assert row is not None and row.state is SessionState.NEEDS_YOU
    assert row.needs_you_reason is not None and cwd in row.needs_you_reason

    # --- absence: and not one key ------------------------------------------
    assert counter.key_argvs() == [], (
        "a bare Enter on the trust dialog selects 'No, exit' (A11) and the session "
        "exits 1; a spawn answers no dialog, ever"
    )
    assert world.events[-1].payload["pane_kind"] == PaneKind.TRUST_DIALOG.value


def test_the_scripted_fast_path_agrees_and_writes_nothing(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The same claim at the fixture seam. Kept **beside** the proof, not as it.

    `ScriptedRunner.writes` can only see `write`; the `LocalRunner` row above is
    what sees a key arriving through any of the other nine members.
    """
    runner = scripted(panes=[trust_pane()])
    result, _ = spawn(
        store=store, runner=runner, workspace_id=workspace_id, cwd=str(root / "repo")
    )
    assert isinstance(result, SpawnOutcome) and result.state is SessionState.NEEDS_YOU
    assert runner.writes == []


# ----- 3 · the three caps, each with its own message --------------------------


def _parent_chain(store: Store, workspace_id: str, cwd: str, depth: int) -> str:
    """A real ancestry `depth` deep, through the store's own verb."""
    parent: str | None = None
    for level in range(depth + 1):
        session_id = f"01PARENT000000000000000{level:03d}"[:26]
        store.create_owned_session(
            session_id=session_id,
            engine_session_id=f"parent-{level}",
            workspace_id=workspace_id,
            repo_id=None,
            cwd=cwd,
            started_at=NOW,
            origin=Origin.ORCHESTRATOR,
            parent_session_id=parent,
            depth=level,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=RunnerHandle(runner="local", socket=SOCKET, session_name="shepherd_x"),
            model=None,
            effort=None,
        )
        parent = session_id
    assert parent is not None
    return parent


def test_depth_children_and_total_caps_each_refuse_with_their_own_message(
    store: Store, workspace_id: str, root: Path
) -> None:
    """§11's three caps, and three refusals a caller can act on differently.

    Goes red if one message serves all three: the agent reading "cap exceeded"
    cannot tell "spawn from a shallower parent" from "wait for a pane to free".
    """
    cwd = str(root / "repo")
    refusals: dict[str, SpawnRefused] = {}

    deep_parent = _parent_chain(store, workspace_id, cwd, MAX_SESSION_DEPTH - 1)
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=cwd,
        parent_session_id=deep_parent,
    )
    assert isinstance(result, SpawnRefused), result
    refusals[CAP_DEPTH] = result

    busy_parent = _parent_chain(store, workspace_id, cwd, 0)
    for index in range(MAX_CHILDREN_PER_SESSION):
        store.create_owned_session(
            session_id=f"01CHILD0000000000000000{index:02d}"[:26],
            engine_session_id=f"child-{index}",
            workspace_id=workspace_id,
            repo_id=None,
            cwd=cwd,
            started_at=NOW,
            origin=Origin.ORCHESTRATOR,
            parent_session_id=busy_parent,
            depth=1,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=None,
            model=None,
            effort=None,
        )
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=cwd,
        parent_session_id=busy_parent,
    )
    assert isinstance(result, SpawnRefused), result
    refusals[CAP_CHILDREN] = result

    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()], owned=owned_panes(MAX_TOTAL_OWNED_SESSIONS)),
        workspace_id=workspace_id,
        cwd=cwd,
    )
    assert isinstance(result, SpawnRefused), result
    refusals[CAP_TOTAL] = result

    assert sorted(refusals) == sorted({CAP_DEPTH, CAP_CHILDREN, CAP_TOTAL})
    assert [found.cap for found in refusals.values()] == [CAP_DEPTH, CAP_CHILDREN, CAP_TOTAL]
    reasons = {found.reason for found in refusals.values()}
    assert len(reasons) == 3, f"one message cannot serve three caps: {reasons}"
    for cap, found in refusals.items():
        assert cap in found.reason, f"{found.reason!r} does not name its cap {cap!r}"
    assert str(MAX_SESSION_DEPTH) in refusals[CAP_DEPTH].reason
    assert str(MAX_CHILDREN_PER_SESSION) in refusals[CAP_CHILDREN].reason
    assert str(MAX_TOTAL_OWNED_SESSIONS) in refusals[CAP_TOTAL].reason


def test_the_total_cap_counts_panes_not_rows(
    store: Store, workspace_id: str, root: Path
) -> None:
    """Revision 2's correction, asserted in **both** directions.

    A handle-less row can never be terminated, so a row-counting cap lets orphans
    accumulate across every restart while each holds a live `claude`. Goes red if
    the cap reads `owned_session_counts` alone — and equally red if it starts
    refusing on rows whose panes are gone.
    """
    cwd = str(root / "repo")
    store.create_owned_session(
        session_id="01HANDLELESS000000000000AA"[:26],
        engine_session_id="orphan-1",
        workspace_id=workspace_id,
        repo_id=None,
        cwd=cwd,
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=None,
        model=None,
        effort=None,
    )
    assert store.owned_session_counts() == (1, 1)

    # One row, twenty panes: the cap is full and the rows cannot see it.
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()], owned=owned_panes(MAX_TOTAL_OWNED_SESSIONS)),
        workspace_id=workspace_id,
        cwd=cwd,
    )
    assert isinstance(result, SpawnRefused) and result.cap == CAP_TOTAL

    # The other direction: rows without panes hold no slot.
    for index in range(MAX_TOTAL_OWNED_SESSIONS):
        store.create_owned_session(
            session_id=f"01ROWONLY00000000000000{index:03d}"[:26],
            engine_session_id=f"rowonly-{index}",
            workspace_id=workspace_id,
            repo_id=None,
            cwd=cwd,
            started_at=NOW,
            origin=Origin.ORCHESTRATOR,
            parent_session_id=None,
            depth=0,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=None,
            model=None,
            effort=None,
        )
    assert store.owned_session_counts()[0] > MAX_TOTAL_OWNED_SESSIONS
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=cwd,
    )
    assert isinstance(result, SpawnOutcome), (
        "twenty-one rows and no panes is twenty-one sessions nothing is running"
    )


# ----- 4 · the registered roots (§13) ----------------------------------------


#: The five shapes an unregistered directory arrives in. A named constant so the
#: **count** is asserted (T6/T8/T9's discipline): a parametrize list that shrinks
#: to one case still passes, and shrinks to zero in silence.
ROOT_CASES: tuple[str, ...] = (
    "outside",
    "traversal",
    "traversal_absolute",
    "sibling_prefix",
    "symlink_out",
)


def test_the_root_cases_are_the_five_shapes_they_claim_to_be() -> None:
    assert len(ROOT_CASES) == 5
    assert len(set(ROOT_CASES)) == 5


@pytest.mark.parametrize("case", ROOT_CASES)
def test_spawn_refuses_an_unregistered_directory(
    store: Store, workspace_id: str, root: Path, tmp_path: Path, case: str
) -> None:
    """§13: canonicalize first, then compare — no path traversal into an
    unregistered directory.

    Five shapes, because a rule tested only against the form its author had in
    mind is untested against the form its defeater will use: an unrelated
    absolute path, a `../` escape, a `../` escape spelled from the root itself, a
    **sibling whose name is a string prefix** of the root (`work-other` vs
    `work`), and a symlink inside the root pointing out of it.
    """
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    sibling = tmp_path / "work-other"
    sibling.mkdir()
    link = root / "escape"
    link.symlink_to(outside)
    cwds = {
        "outside": str(outside),
        "traversal": f"{root}/repo/../../elsewhere",
        "traversal_absolute": f"{root}/../elsewhere",
        "sibling_prefix": str(sibling),
        "symlink_out": str(link),
    }

    result, world = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=cwds[case],
    )
    assert isinstance(result, SpawnRefused), f"{case}: {result}"
    assert result.cap is None, "an unregistered directory is not a cap refusal"
    assert cwds[case] in result.reason
    assert store.list_sessions(workspace_id=workspace_id) == [], "refused before any row"
    assert world.events == [], "nothing is published for a spawn that never happened"


def test_a_registered_root_is_accepted_including_the_root_itself(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The negative control: a rule that refuses everything refuses nothing.

    Both the root and a directory under it are accepted, so the check above is
    proved to stay *quiet* as well as to fire.
    """
    for cwd in (str(root), str(root / "repo")):
        result, _ = spawn(
            store=store,
            runner=scripted(panes=[ready_pane()]),
            workspace_id=workspace_id,
            cwd=cwd,
        )
        assert isinstance(result, SpawnOutcome), f"{cwd}: {result}"


def test_a_workspace_with_no_registered_root_refuses(store: Store, root: Path) -> None:
    """A project nobody registered a repo to is not an allowlist of everything."""
    rootless = store.create_project(name="rootless", description=None).id
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=rootless,
        cwd=str(root / "repo"),
    )
    assert isinstance(result, SpawnRefused)
    assert "no registered repo" in result.reason


# ----- 5 · no tmux is a refusal, not a traceback ------------------------------


def test_no_tmux_is_a_refusal_not_a_traceback(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The binary is gone: `LocalRunner` raises `RunnerRefusal` and nothing else
    may reach the tool surface.

    Driven through the real driver's own `FileNotFoundError` path, so the counted
    `TMUX_UNAVAILABLE` and the refusal are the shipped ones rather than a fixture's.
    """
    anomalies: list[Anomaly] = []

    def absent(argv: list[str]) -> CommandResult:
        raise FileNotFoundError(2, "No such file or directory", "tmux")

    runner = dataclasses.replace(
        local_runner(CountingTmux(READY_CAPTURE, LIVE_FIELDS), anomalies), run_argv=absent
    )
    result, world = spawn(
        store=store, runner=runner, workspace_id=workspace_id, cwd=str(root / "repo")
    )
    assert isinstance(result, SpawnRefused), result
    assert "tmux is not available" in result.reason
    assert result.cap is None
    assert [found.kind for found in anomalies] == [AnomalyKind.TMUX_UNAVAILABLE]
    assert world.events == []
    assert store.list_sessions(workspace_id=workspace_id) == [], (
        "the pane driver is unreachable, so D-5 refuses before any row exists"
    )


def test_an_ensure_server_that_refuses_is_a_refusal_not_a_traceback(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The second half the plan names, and a gap a surviving mutation found.

    Removing the `try` around steps 5's two calls left
    `test_no_tmux_is_a_refusal_not_a_traceback` **green**, because an absent
    binary is already refused at admission — the start-level guard was held only
    by the C-M3-7 test, incidentally. A server that cannot be started is the case
    that reaches it on purpose: the pane driver answered the probe and then the
    launch failed, which is DP5's detached launch failing on a real host.
    """
    world = Spawned(ensure_server_refusal="no server on the socket, and none could be started")
    runner = scripted(panes=[ready_pane()])
    result, _ = spawn(
        store=store,
        runner=runner,
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=world,
    )
    assert isinstance(result, SpawnRefused), result
    assert "no server on the socket" in result.reason
    assert world.ensure_server_calls == 1
    assert "start" not in runner.calls, "nothing may be started when the server is not there"
    rows = store.list_sessions(workspace_id=workspace_id)
    assert len(rows) == 1 and rows[0].runner_handle is None, (
        "the row still exists first (C-M3-7): T12's reconcile is what adopts it"
    )


def test_a_host_with_no_pane_driver_cannot_spawn_and_says_so(
    store: Store, workspace_id: str, root: Path
) -> None:
    """D-5 through `capabilities(pane_driver_available=...)`, never the constant.

    Goes red if `can_spawn` is read off the module constant, which is `True`
    unconditionally: the refusal would never fire on a host with no pane driver.
    """

    class NoDriver:
        def list_owned_panes(self) -> tuple[PaneRef, ...]:
            raise RunnerRefusal("no server running on this socket, and none can be started")

        def start(self, spec: SessionSpec) -> RunnerHandle:  # pragma: no cover
            raise AssertionError("a host that cannot spawn must not reach start")

    result, _ = spawn(
        store=store, runner=NoDriver(), workspace_id=workspace_id, cwd=str(root / "repo")
    )
    assert isinstance(result, SpawnRefused)
    assert "can_spawn" in result.reason, result.reason


# ----- 6 · the poll resolves, and a fourth outcome is counted -----------------


def test_the_poll_outcome_table_is_total_over_pane_kind() -> None:
    """Six kinds in, three decisions and three keep-polling — and no gap.

    A set equality against the enum, never a length: a dropped row would leave a
    kind the poll cannot label, which is the fourth outcome escaping unlabelled.
    """
    assert set(POLL_OUTCOME) == set(PaneKind)
    decided = {kind: state for kind, state in POLL_OUTCOME.items() if state is not None}
    assert decided == {
        PaneKind.PROMPT_READY: SessionState.STARTING,
        PaneKind.TRUST_DIALOG: SessionState.NEEDS_YOU,
        PaneKind.DEAD: SessionState.STOPPED,
    }


#: Six scripts: each decisive kind alone, and each undecided kind followed by a
#: decisive one. Named so the count **and** the coverage can be asserted against
#: the enum — a dropped script would leave a kind the suite never drives.
RESOLUTION_CASES: tuple[tuple[tuple[PaneKind, ...], SessionState], ...] = (
    ((PaneKind.PROMPT_READY,), SessionState.STARTING),
    ((PaneKind.TRUST_DIALOG,), SessionState.NEEDS_YOU),
    ((PaneKind.DEAD,), SessionState.STOPPED),
    ((PaneKind.BUSY, PaneKind.PROMPT_READY), SessionState.STARTING),
    ((PaneKind.UNREADABLE, PaneKind.TRUST_DIALOG), SessionState.NEEDS_YOU),
    ((PaneKind.PERMISSION_DIALOG, PaneKind.DEAD), SessionState.STOPPED),
)


def test_the_resolution_cases_drive_every_pane_kind() -> None:
    """The count, and the coverage it is a count of."""
    assert len(RESOLUTION_CASES) == 6
    assert {kind for script, _ in RESOLUTION_CASES for kind in script} == set(PaneKind)
    assert {state for _, state in RESOLUTION_CASES} == {
        SessionState.STARTING,
        SessionState.NEEDS_YOU,
        SessionState.STOPPED,
    }


@pytest.mark.parametrize(("script", "state"), RESOLUTION_CASES)
def test_spawn_resolves_to_one_of_three_pane_states(
    store: Store,
    workspace_id: str,
    root: Path,
    script: tuple[PaneKind, ...],
    state: SessionState,
) -> None:
    """A scripted pane sequence resolves to exactly one of the three outcomes.

    The undecided kinds are polled **through**, not answered: a spawn that
    labelled `BUSY` as ready would report a session that has shown nothing.
    """
    by_kind = {
        PaneKind.PROMPT_READY: ready_pane(),
        PaneKind.TRUST_DIALOG: trust_pane(),
        PaneKind.DEAD: dead_pane(),
        PaneKind.UNREADABLE: unreadable_pane(),
        PaneKind.BUSY: dataclasses.replace(ready_pane(), kind=PaneKind.BUSY),
        PaneKind.PERMISSION_DIALOG: dataclasses.replace(
            ready_pane(), kind=PaneKind.PERMISSION_DIALOG
        ),
    }
    result, world = spawn(
        store=store,
        runner=scripted(panes=[by_kind[kind] for kind in script]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
    )
    assert isinstance(result, SpawnOutcome), result
    assert result.state is state
    row = store.get_owned_session(result.session_id)
    assert row is not None and row.state is state
    assert len(world.events) == 1 and world.events[0].kind == SPAWN_EVENT


def test_a_dead_pane_carries_its_exit_code_to_the_row(
    store: Store, workspace_id: str, root: Path
) -> None:
    """E-M3-16/C15: a refused trust dialog exits 1; the capture here exits 143.

    The status comes off `pane_dead_status` in the real listing fields, so a
    spawn that dropped it would leave an end nobody can read (G-M2-2).
    """
    result, world = spawn(
        store=store,
        runner=scripted(panes=[dead_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
    )
    assert isinstance(result, SpawnOutcome) and result.state is SessionState.STOPPED
    assert "143" in result.detail, result.detail
    assert world.events[0].payload["exit_code"] == 143


def test_a_pane_that_never_decides_is_needs_you_and_is_counted(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The fourth outcome: labelled, bounded, and **counted** (principle 5).

    Goes red if the timeout silently returns `starting` — a session reported live
    that nothing has ever read — or if the unknown is not counted where `doctor`
    reads it.
    """
    before = store.list_anomaly_counts().get(AnomalyKind.PANE_UNREADABLE.value, 0)
    result, world = spawn(
        store=store,
        runner=scripted(panes=[unreadable_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
    )
    assert isinstance(result, SpawnOutcome), result
    assert result.state is SessionState.NEEDS_YOU
    assert "60" in result.detail and "unreadable" in result.detail, result.detail
    after = store.list_anomaly_counts().get(AnomalyKind.PANE_UNREADABLE.value, 0)
    assert after == before + 1, "an unknown that is not counted is an unknown that is hidden"
    assert world.events[0].payload["pane_kind"] == PaneKind.UNREADABLE.value


# ----- 7 · the sequence's order and its publication ---------------------------


def test_the_server_is_ensured_before_the_pane_is_started(
    store: Store, workspace_id: str, root: Path
) -> None:
    """DP5: a server first started inside the daemon's cgroup dies with the unit."""
    runner = scripted(panes=[ready_pane()])
    world = Spawned()
    spawn(
        store=store,
        runner=runner,
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=world,
    )
    assert world.ensure_server_calls == 1
    assert runner.calls[0] == "list_owned_panes"


def test_the_handle_is_bound_and_the_spawn_is_published_once(
    store: Store, workspace_id: str, root: Path
) -> None:
    """Step 5's `set_runner_handle` and step 8's one event."""
    result, world = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
    )
    assert isinstance(result, SpawnOutcome)
    row = store.get_owned_session(result.session_id)
    assert row is not None and row.runner_handle is not None
    assert row.runner_handle.session_name == f"shepherd_{result.session_id}"
    assert [event.kind for event in world.events] == [SPAWN_EVENT]
    assert world.events[0].session_id == result.session_id


def test_a_known_untrusted_directory_is_named_before_the_spawn(
    store: Store, workspace_id: str, root: Path, tmp_path: Path
) -> None:
    """Step 3: the pre-flight verdict is published, not discovered afterwards.

    The engine's config says `hasTrustDialogAccepted: false` and the pane comes
    up ready anyway; the fact still reaches the caller, because "this will stop
    on a dialog" is worth knowing in advance.
    """
    cwd = str(root / "repo")
    result, world = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=cwd,
        engine_config_home=trusted_home(tmp_path, cwd, trusted=False),
    )
    assert isinstance(result, SpawnOutcome)
    assert world.events[0].payload["trusted"] is False
    assert cwd in str(world.events[0].payload["trust_source"])


def test_an_unknown_trust_verdict_stays_unknown(
    store: Store, workspace_id: str, root: Path
) -> None:
    """No config home named: `trusted` is `None` and says why (principle 5)."""
    result, world = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        engine_config_home=None,
    )
    assert isinstance(result, SpawnOutcome)
    assert world.events[0].payload["trusted"] is None
    assert world.events[0].payload["trust_source"] != ""


def test_the_engine_config_home_is_required_at_the_call_site() -> None:
    """T10-R2's shape, carried up: "I have none" is a decision somebody typed.

    Goes red if the parameter gains a default — the exact shape whose default was
    the user's real 97 KB config (T10-R1).
    """
    import inspect

    parameter = inspect.signature(spawn_owned_session).parameters["engine_config_home"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_the_modules_stay_small() -> None:
    """The plan's artifact: ≤ 300 lines.

    The sequence and its admission came to 367 together, and this repo has
    answered that collision with a split five times rather than by raising a cap
    (`rows.py`, `stops.py`, `signals/fields.py`, `reads.py`, `writes.py`). Both
    halves are asserted, so the split cannot become a way of hiding growth.
    """
    for module in (MODULE, ADMISSION):
        lines = len(module.read_text(encoding="utf-8").splitlines())
        assert lines <= 300, f"{module.name} is {lines} lines"


def test_the_refusal_type_is_one_class_not_two() -> None:
    """`spawn.SpawnRefused` is `admission.SpawnRefused` — an alias, not a copy.

    Two structurally identical dataclasses are the split `mypy` only catches
    where they happen to meet (M1's F9), and `isinstance` at the call site is
    what a caller uses to tell a refusal from an outcome.
    """
    from shepherd.orchestration import admission

    assert SpawnRefused is admission.SpawnRefused
