"""P-M3-9's orchestration half: every public callable, fed garbage, counted.

**The property.** Every public callable under `src/shepherd/orchestration/`,
driven with the degraded inputs P-M3-9 names — the whole of one real capture
truncated at **every byte boundary**, plus empty, non-UTF-8, a sidecar path that
is a directory, and an absent sidecar — returns a value and raises nothing, and
every anomaly the run counts is a **named `AnomalyKind` member** rather than a
bare string.

**The enumeration rule, written down so a future reader can tell a shrinking
population from a changed rule** (this is the whole reason the plan's literal
`17` is not used; see below):

1. **Modules**: every module `pkgutil.iter_modules()` finds directly under the
   `shepherd.orchestration` package whose name does not begin with `_`. A
   package listing, never a hand-kept list — M2's acceptance clause 2 lesson.
2. **Names**: the module's `__all__` when it has one, otherwise every
   module-level name not beginning with `_`. Both halves are needed:
   `write_policy.py` has no `__all__`, so an `__all__`-only rule cannot see
   `decide_write` — the rule that produced the router's count of 22 where the
   plan said 17.
3. **Kept**: names bound to a **function defined in that module**
   (`inspect.isfunction` and `__module__ == module.__name__`). This excludes
   classes and Protocols (`SpawnRefused`, `ForkRunner`), enums, typing aliases
   (`PermissionChoice` is a `Literal`, and counting it twice is one of the two
   ways the plan's number went wrong), and every re-export — a re-exported
   function is driven where it is written, and driving it twice would report
   coverage this suite does not have.

**The count is measured, never typed.** The plan says "assert the enumerated
count equals 17"; the population was 22 when T20 measured it and is 22 today,
and a literal would have been wrong on the day it was written. So the assertion
is a **set equality** against `POPULATION` below — which turns red when a
callable is added *or* removed, where a length would miss a swap (T13's lesson
at clause 4, in a different suit). The case count is likewise computed from the
capture that is read at test time and asserted against what the generator
produced, because "revision 1's generator could not reach its own number".

Seam: each module's public interface, driven directly. Not `invoke()`: half of
this population is not behind a capability, and the property is about the
functions, not about the surface.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

import shepherd.orchestration as orchestration_package
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.mailbox import MailboxOrigin
from shepherd.core.master import MasterEvent
from shepherd.core.runner import (
    EngineCapabilities,
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    WriteDecision,
)
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import Bucket
from shepherd.orchestration import (
    admission,
    ask,
    dialog_keys,
    dialogs,
    lifecycle,
    mailbox,
    master_turn,
    rename,
    spawn,
    wake,
    write_policy,
)
from shepherd.runner.base import PaneRef
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The capture P-M3-9 itself argues over: 154 bytes, whole, and truncated at
#: every one of its byte boundaries. A *whole* capture, not its last line —
#: revision 1 truncated the last line only and could not reach its own number.
CAPTURE = (
    REPO_ROOT
    / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui"
    / "run-20260914T154946Z" / "13-dead-pane.txt"
).read_bytes()

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"

NOW = "2026-09-17T10:00:00.000Z"
PID = 4041880
OWNED_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
OWNED_NAME = f"shepherd_{OWNED_ID}"
ENGINE_ID = "11111111-2222-3333-4444-555555555555"

#: The engine's record as it ships (`can_set_title` **False**, D29/DP1). A value,
#: never the module constant: `capabilities()` has its own permitted callers.
CEILING = EngineCapabilities(
    can_spawn=True,
    can_steer=True,
    can_fork=True,
    can_set_title=False,
    has_hooks=True,
    effort_ladder=("low", "medium", "high", "xhigh", "max"),
    transcript_format="jsonl",
)

#: The degradations this tree does **not** survive, pinned rather than hidden.
#:
#: **Empty, and that is a result rather than a default.** T23 found exactly one:
#: `admission.admit` resolved the caller's `cwd` with `Path(cwd).resolve()`, and
#: a string containing a NUL raised `ValueError: embedded null byte` out of the
#: verb — reachable from the browser (`POST /api/sessions` with a `cwd` carrying
#: `\u0000`), and flattened by `invoke()` into `Failure.FAILED` + `"ValueError"`,
#: which is precisely the "a page cannot tell a refusal from a crash" outcome
#: principle 5 forbids. `admit` now answers `SpawnRefused` for every string
#: `resolve()` will not accept, on both sides of the rule — the caller's `cwd`
#: and the registered roots — and the entry was deleted with the fix, which is
#: the move the set-equality below exists to demand.
#:
#: Compared as a **set**, so this is not a mute: a *new* escape is red, and so is
#: **fixing one** without deleting its entry — whoever repairs an escape is told
#: by the suite rather than left to notice.
KNOWN_DEFECTS: frozenset[str] = frozenset()

#: The 22 this tree has, as `(module, name)` pairs — the *measured* population,
#: not the plan's `17`. Compared as a **set**: red when one is added, red when
#: one is dropped, and red on a swap that keeps the length.
POPULATION: frozenset[tuple[str, str]] = frozenset(
    {
        ("admission", "admit"),
        ("ask", "ask_session"),
        ("dialog_keys", "is_the_captured_permission_dialog"),
        ("dialog_keys", "is_the_captured_trust_dialog"),
        ("dialogs", "answer_permission"),
        ("dialogs", "answer_trust"),
        ("lifecycle", "interrupt_session"),
        ("lifecycle", "observe_exit"),
        ("lifecycle", "rebind"),
        ("lifecycle", "reconcile_owned_panes"),
        ("lifecycle", "record_and_terminate"),
        ("mailbox", "coalesce"),
        ("mailbox", "deliver_now"),
        ("mailbox", "queue_message"),
        ("mailbox", "sweep_pending"),
        ("mailbox", "turn_state"),
        # T27's turn driver. `TurnDriver`, `TurnStarted` and `TurnRefused` are
        # classes, so rule 3 excludes them and `project_to_stream` is the whole
        # of this module's population.
        ("master_turn", "project_to_stream"),
        ("rename", "confirm_engine_title"),
        ("rename", "drive_engine_rename"),
        ("rename", "rename_session"),
        ("spawn", "spawn_owned_session"),
        ("wake", "drain"),
        ("wake", "peek"),
        ("wake", "render_wake_text"),
        ("write_policy", "decide_write"),
        ("write_policy", "refusal_text"),
    }
)


# ----- the enumeration rule, as code ------------------------------------------


def orchestration_modules() -> list[ModuleType]:
    """Rule 1: every public module the package listing finds."""
    return [
        importlib.import_module(f"{orchestration_package.__name__}.{found.name}")
        for found in sorted(
            pkgutil.iter_modules(orchestration_package.__path__), key=lambda m: m.name
        )
        if not found.name.startswith("_")
    ]


def public_callables(module: ModuleType) -> list[str]:
    """Rules 2 and 3, for one module."""
    declared = getattr(module, "__all__", None)
    names = list(declared) if declared else [n for n in vars(module) if not n.startswith("_")]
    return sorted(
        name
        for name in names
        if inspect.isfunction(getattr(module, name, None))
        and getattr(module, name).__module__ == module.__name__
    )


def enumerated_population() -> frozenset[tuple[str, str]]:
    return frozenset(
        (module.__name__.rsplit(".", 1)[-1], name)
        for module in orchestration_modules()
        for name in public_callables(module)
    )


# ----- the degradations -------------------------------------------------------

#: What the sidecar *is* for a case, when it is not bytes.
SIDECAR_ABSENT = "absent"
SIDECAR_DIRECTORY = "directory"


@dataclass(frozen=True)
class Case:
    """One degraded world: what the screen shows and what the sidecar is."""

    name: str
    screen: bytes
    sidecar: bytes | str


def degradations() -> list[Case]:
    """The set P-M3-9 names, generated rather than listed."""
    cases = [
        Case(f"truncated@{index}", CAPTURE[:index], CAPTURE[:index])
        for index in range(len(CAPTURE) + 1)
    ]
    cases.append(Case("empty", b"", b""))
    cases.append(Case("not-utf-8", b"\xff\xfe\x00\x80", b"\xff\xfe\x00\x80"))
    cases.append(Case("whole-capture", CAPTURE, CAPTURE))
    cases.append(Case("sidecar-is-a-directory", CAPTURE, SIDECAR_DIRECTORY))
    cases.append(Case("sidecar-absent", CAPTURE, SIDECAR_ABSENT))
    return cases


@dataclass(frozen=True)
class World:
    """Everything the 22 need, rebuilt per case around the degraded bytes."""

    store: Store
    runner: ScriptedRunner
    handle: RunnerHandle
    pane: PaneState
    config_dir: Path
    text: str


def refusing_fork(argv: list[str], *, timeout_ms: int) -> object:
    """`ask()`'s process seam, refusing: no test here starts a process."""
    raise RunnerRefusal("no fork runs in a degradation suite")


def place_sidecar(config_dir: Path, case: Case) -> None:
    """Put this case's sidecar where `confirm_engine_title` will look for it.

    Three shapes, all of them real: the degraded bytes, a path that is a
    **directory** (a read raises `IsADirectoryError`, which is an `OSError` only
    if somebody remembered), and no file at all.
    """
    sidecar = config_dir / "sessions" / f"{PID}.json"
    if sidecar.is_dir():
        sidecar.rmdir()
    elif sidecar.exists():
        sidecar.unlink()
    if isinstance(case.sidecar, bytes):
        sidecar.write_bytes(case.sidecar)
    elif case.sidecar == SIDECAR_DIRECTORY:
        sidecar.mkdir()


def build_world(store: Store, config_dir: Path, case: Case) -> World:
    """The degraded bytes, placed everywhere an orchestration verb can meet them.

    A **fresh runner per call**, not per case: `record_and_terminate` really does
    end the pane, and a shared fixture would turn every entry point driven after
    it into "no such pane" — a suite that passed because it stopped reaching the
    code it claims to degrade.

    The pane classifier is the shipped one (`runner/pane.py`), so what reaches
    `decide_write` and `turn_state` is what a real degraded capture becomes —
    not a `PaneState` this test typed, which would prove only that the test and
    the classifier agree.
    """
    pane = read_pane(case.screen, parse_pane_fields(LIVE_FIELDS), [])
    runner = ScriptedRunner(
        panes=(pane,),
        proc=ProcState(alive=True, pid=PID, exit_code=None, exit_signal=None, observed_at=NOW),
        screen=case.screen,
        owned_panes=(
            PaneRef(session_name=OWNED_NAME, session_id=OWNED_ID, pane_pid=PID, dead=False),
            # An **orphan**, so `reconcile_owned_panes` drives its "not ours"
            # branch too. Without it that branch is unreached here, and a
            # mutation planting a bare-string anomaly in it survived this suite
            # (T23 mutation m12) — a hole found by mutating, not by reading.
            PaneRef(session_name="shepherd_not-one-of-ours", session_id="x", pane_pid=None,
                    dead=True),
        ),
    )
    return World(
        store=store,
        runner=runner,
        handle=RunnerHandle(
            runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=OWNED_NAME
        ),
        pane=pane,
        config_dir=config_dir,
        text=case.screen.decode("utf-8", "replace"),
    )


# ----- one driver per entry point, keyed by the enumeration -------------------


def drivers(world: World, workspace_id: str, index: int) -> dict[tuple[str, str], Callable[[], object]]:
    """Every member of `POPULATION`, bound to this case's degraded world.

    The keys are asserted equal to the enumerated population, so a callable that
    appears in `orchestration/` and not here fails loudly rather than going
    undriven — which is the failure mode a count could never catch.
    """
    store, runner, handle = world.store, world.runner, world.handle
    queued = store.pending_for(OWNED_ID)
    return {
        ("admission", "admit"): lambda: admission.admit(
            store=store,
            runner=runner,
            workspace_id=workspace_id,
            cwd=world.text or "/tmp",
            parent_session_id=None,
        ),
        ("ask", "ask_session"): lambda: ask.ask_session(
            store=store,
            run_fork=refusing_fork,
            now=lambda: NOW,
            binary="claude",
            projects_root=world.config_dir / "projects",
            can_fork=True,
            session_id=OWNED_ID,
            question=world.text,
        ),
        ("dialog_keys", "is_the_captured_permission_dialog"): (
            lambda: dialog_keys.is_the_captured_permission_dialog(world.text)
        ),
        ("dialog_keys", "is_the_captured_trust_dialog"): (
            lambda: dialog_keys.is_the_captured_trust_dialog(world.text)
        ),
        ("dialogs", "answer_permission"): lambda: dialogs.answer_permission(
            store=store,
            runner=runner,
            handle=handle,
            session_id=OWNED_ID,
            choice="approve",
            sidecar=dialog_keys.SidecarState.WAITING,
        ),
        ("dialogs", "answer_trust"): lambda: dialogs.answer_trust(
            runner=runner, handle=handle, session_id=OWNED_ID, trust=True
        ),
        ("lifecycle", "interrupt_session"): lambda: lifecycle.interrupt_session(
            store=store,
            runner=runner,
            handle=handle,
            session_id=OWNED_ID,
            now=lambda: NOW,
            publish=lambda event: None,
        ),
        ("lifecycle", "observe_exit"): lambda: lifecycle.observe_exit(
            runner=runner, handle=handle
        ),
        ("lifecycle", "rebind"): lambda: lifecycle.rebind(
            store=store, session_id=OWNED_ID, new_engine_session_id=f"{ENGINE_ID}-{index}"
        ),
        ("lifecycle", "reconcile_owned_panes"): lambda: lifecycle.reconcile_owned_panes(
            store=store,
            runner=runner,
            now=lambda: NOW,
            runner_name=RUNNER_NAME,
            socket=SCRIPTED_SOCKET,
        ),
        ("lifecycle", "record_and_terminate"): lambda: lifecycle.record_and_terminate(
            store=store,
            runner=runner,
            handle=handle,
            session_id=OWNED_ID,
            now=lambda: NOW,
            publish=lambda event: None,
        ),
        ("mailbox", "coalesce"): lambda: mailbox.coalesce(queued),
        ("mailbox", "deliver_now"): lambda: mailbox.deliver_now(
            store=store,
            runner=runner,
            handle=handle,
            session_id=OWNED_ID,
            state=SessionState.RUNNING,
            ownership=Ownership.OWNED,
            now=lambda: NOW,
        ),
        ("mailbox", "queue_message"): lambda: mailbox.queue_message(
            store=store,
            session_id=OWNED_ID,
            body=world.text,
            origin=MailboxOrigin.USER_UI,
            idempotency_key=f"degradation.{index}",
            now=lambda: NOW,
        ),
        ("mailbox", "sweep_pending"): lambda: mailbox.sweep_pending(
            store=store, runner=runner, now=lambda: NOW, handles={OWNED_ID: handle}
        ),
        ("mailbox", "turn_state"): lambda: mailbox.turn_state(
            SessionState.RUNNING, world.pane, Ownership.OWNED
        ),
        # T27's projection, driven against the degraded bytes in every field a
        # `MasterEvent` has: an event whose kind is unreadable, whose text and
        # tool name are the degraded screen, and whose payload carries it too.
        ("master_turn", "project_to_stream"): lambda: master_turn.project_to_stream(
            MasterEvent(
                kind="text",
                text=world.text,
                tool_name=world.text or None,
                payload={"detail": world.text, master_turn.MASTER_SESSION_KEY: world.text},
                occurred_at=world.text,
            ),
            world.text or "01TURN",
        ),
        ("rename", "confirm_engine_title"): lambda: rename.confirm_engine_title(
            config_dir=world.config_dir, pid=PID, title=world.text
        ),
        ("rename", "drive_engine_rename"): lambda: rename.drive_engine_rename(
            runner=runner, handle=handle, title=world.text
        ),
        ("rename", "rename_session"): lambda: rename.rename_session(
            store=store,
            runner=runner,
            handle=handle,
            session_id=OWNED_ID,
            title=world.text or "untitled",
            now=lambda: NOW,
            capabilities=CEILING,
            ownership=Ownership.OWNED,
            config_dir=world.config_dir,
        ),
        ("spawn", "spawn_owned_session"): lambda: spawn.spawn_owned_session(
            store=store,
            runner=runner,
            now=lambda: NOW,
            sleep=lambda seconds: None,
            publish=lambda event: None,
            ensure_server=lambda: None,
            engine_config_home=world.config_dir,
            workspace_id=workspace_id,
            cwd=str(world.config_dir),
            brief=world.text,
            title=None,
            model=None,
            effort=None,
            parent_session_id=None,
            origin=Origin.USER_UI,
        ),
        # T9's wake set. `drain` and `peek` are driven against the degraded
        # world's store; `render_wake_text` is driven against the degraded
        # *text* itself, as a title and a `why`, because that is the only place
        # a screen capture can reach this module at all.
        ("wake", "drain"): lambda: wake.drain(store, lambda: NOW),
        ("wake", "peek"): lambda: wake.peek(store),
        ("wake", "render_wake_text"): lambda: wake.render_wake_text(
            wake.WakeSummary(
                items=(
                    wake.WakeItem(
                        session_id=OWNED_ID,
                        title=world.text,
                        bucket=Bucket.ERROR,
                        why=world.text,
                        first_action=None,
                    ),
                ),
                drained_at=world.text,
            )
        ),
        ("write_policy", "decide_write"): lambda: write_policy.decide_write(
            SessionState.RUNNING, world.pane, Ownership.OWNED
        ),
        ("write_policy", "refusal_text"): lambda: write_policy.refusal_text(
            WriteDecision.REFUSE_NO_PTY
        ),
    }


def returns_a_value(module_name: str, name: str) -> bool:
    """Does this entry point's own signature promise a value?

    Read off the annotation rather than assumed: `interrupt_session` and
    `rebind` are declared `-> None`, and demanding a value from them would be
    this test inventing a contract the seam never made.
    """
    module = importlib.import_module(f"{orchestration_package.__name__}.{module_name}")
    annotation = inspect.signature(getattr(module, name)).return_annotation
    return str(annotation).strip("'\"") not in {"None", "NoneType"}


@pytest.fixture()
def world_store(tmp_path: Path) -> Iterator[tuple[Store, Path, str]]:
    """One store, one engine config dir, one registered workspace root."""
    config_dir = tmp_path / "engine-config"
    (config_dir / "sessions").mkdir(parents=True)
    (config_dir / "projects").mkdir(parents=True)
    store = open_store(tmp_path / "data" / "shepherd.db")
    try:
        workspace_id = store.upsert_workspace("degradation", str(config_dir)).id
        store.create_owned_session(
            session_id=OWNED_ID,
            engine_session_id=ENGINE_ID,
            workspace_id=workspace_id,
            repo_id=None,
            cwd=str(config_dir),
            started_at=NOW,
            origin=Origin.USER_UI,
            parent_session_id=None,
            depth=0,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=RunnerHandle(
                runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=OWNED_NAME
            ),
            model=None,
            effort=None,
        )
        yield store, config_dir, workspace_id
    finally:
        store.close()


def test_the_enumerated_population_is_the_one_this_suite_drives(
    world_store: tuple[Store, Path, str], tmp_path: Path
) -> None:
    """The rule at the top of this file, applied, compared as a set.

    Goes red when an orchestration module gains a public callable nobody drives,
    when one is dropped, and on a swap that keeps the count — which is the case
    the plan's `== 17` could not have caught.
    """
    store, config_dir, workspace_id = world_store
    enumerated = enumerated_population()

    assert enumerated == POPULATION, {
        "undriven": sorted(enumerated - POPULATION),
        "gone": sorted(POPULATION - enumerated),
    }
    # Arrival: the rule really walked the package and really found functions…
    assert len(orchestration_modules()) == 11
    assert len(enumerated) == 26

    # …and every one of them has a driver, keyed by the same pair.
    place_sidecar(config_dir, degradations()[0])
    world = build_world(store, config_dir, degradations()[0])
    assert set(drivers(world, workspace_id, 0)) == POPULATION


def test_orchestration_degrades_and_counts(world_store: tuple[Store, Path, str]) -> None:
    """P-M3-9: none of the 22 raises on any degradation, and every anomaly the
    run counts is a named `AnomalyKind` member.

    The case count is **computed from the capture read at test time** and
    asserted against the generated list, so the loop cannot shrink silently —
    revision 1's generator "could not reach its own number".

    Goes red if any entry point raises, if a degradation is counted as a bare
    string rather than a named member, if the population and the drivers
    disagree, or if the generator stops reaching every byte boundary.
    """
    store, config_dir, workspace_id = world_store
    cases = degradations()

    # The number this suite computed, from the bytes it actually read.
    expected_cases = len(CAPTURE) + 1 + 5
    assert len(CAPTURE) == 154, "the capture moved; re-read P-M3-9 before touching the number"
    assert len(cases) == expected_cases
    assert len({case.name for case in cases}) == expected_cases

    escaped: list[str] = []
    valueless: list[str] = []
    driven = 0
    for index, case in enumerate(cases):
        place_sidecar(config_dir, case)
        for module_name, name in sorted(POPULATION):
            world = build_world(store, config_dir, case)
            call = drivers(world, workspace_id, index)[(module_name, name)]
            driven += 1
            try:
                answer = call()
            except Exception as error:  # noqa: BLE001 — the property is "none raises"
                escaped.append(f"{case.name}: {module_name}.{name} raised {error!r}")
                continue
            if answer is None and returns_a_value(module_name, name):
                valueless.append(f"{case.name}: {module_name}.{name} returned no value")

    assert set(escaped) == KNOWN_DEFECTS, {
        "new": sorted(set(escaped) - KNOWN_DEFECTS)[:5],
        "fixed — delete it from KNOWN_DEFECTS": sorted(KNOWN_DEFECTS - set(escaped)),
    }
    assert valueless == [], valueless[:5]
    assert driven == expected_cases * len(POPULATION)

    counted = store.list_anomaly_counts()
    named = {str(kind.value) for kind in AnomalyKind}
    # Arrival before absence: the degradations really were counted somewhere…
    assert counted != {}, "no degradation was counted at all; nothing reached a sink"
    # …and every count is one of the named members, never a bare string.
    assert [key for key in counted if key not in named] == []
