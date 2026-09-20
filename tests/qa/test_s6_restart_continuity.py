"""S6 — restart continuity: the plan's premise was false, and the chain works.

**The plan says the reader is missing. It is not, and that is this scenario's
first finding.** `docs/plans/2026-09-18-m1-m4-qa-plan.md` S6 reads
*"`MasterRuntime.resume()` **has no caller in `src/`**. Assert the writer works
and record the missing reader honestly"*, repeating the router's "no caller"
register (§T27-6). Measured on this tree, an AST scan over `src/` finds one
caller: `daemons/plane.py::build_master`, which reads `MASTER_SESSION_KEY` back
out of `app_state` and calls `runtime.resume(conversation)`.

So the honest scenario is not the one the plan describes. What S6 asserts here
is the chain the plan expected to find broken, **end to end**, plus the two
properties the register's own words demand of a closed row:

1. the **writer** — `TurnDriver._remember_session` persists the id the runtime
   reported, first event wins;
2. the **reader** — `plane.build_master` resumes with **exactly** the persisted
   id, which is the one thing a wired-but-wrong reader would get wrong (D10's
   continuity resting on a plausible id that names no transcript is E-M4-8, and
   it would be green in every other test in the tree);
3. a **missing** row resumes nothing rather than resuming the empty string — the
   shipped docstring's own sentence, driven.

And the restart itself: two drivers over one store, the second handed the first
one's conversation.

*Lying implementations this now catches:* a reader that resumes a freshly minted
id (asserted equal to the persisted one, and the persisted one has a distinctive
value no minter would produce); a reader that resumes `""` on a cold start
(driven, and asserted to resume nothing at all); a writer that takes the *last*
event's id rather than the first; and a register row that reopens — the scan
goes red if the caller disappears again.
"""

from __future__ import annotations

import ast
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from shepherd.core.master import MasterEvent, MasterRuntime
from shepherd.orchestration.master_turn import MASTER_SESSION_KEY, TurnDriver, TurnStarted
from shepherd.store.db import Store, open_store

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "shepherd"
BOUNDARY_FIXTURES = REPO_ROOT / "tests" / "boundaries" / "fixtures"

#: The id the scripted runtime reports. Distinctive, so a key written from
#: anywhere else — a ULID minted by the driver, a constant, the turn id — is
#: visible rather than plausible.
RUNTIME_SESSION_ID = "s6-conversation-b0a1c2d3"

NOW = "2026-09-18T10:00:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


class ReportingMaster:
    """A runtime that reports its conversation id the way a real one does.

    `AgentSDKMaster` puts `master_session_id` on the payload of the events it
    projects; this reports the same key with the same spelling, which is the
    seam's contract and not this file's invention.
    """

    def __init__(self, session_id: str = RUNTIME_SESSION_ID) -> None:
        self.session_id = session_id
        self.resumed: list[str] = []
        self.closed = 0
        self.prompts: list[str] = []

    def configure(self, tools: tuple[object, ...], system_prompt: str) -> None:
        pass

    def send(self, text: str) -> AsyncIterator[MasterEvent]:
        self.prompts.append(text)

        async def stream() -> AsyncIterator[MasterEvent]:
            yield MasterEvent(
                kind="turn_started",
                text=None,
                tool_name=None,
                payload={MASTER_SESSION_KEY: self.session_id},
                occurred_at=NOW,
            )
            yield MasterEvent(
                kind="turn_ended", text="done", tool_name=None, payload={}, occurred_at=NOW
            )

        return stream()

    def resume(self, master_session_id: str) -> None:
        self.resumed.append(master_session_id)

    def interrupt(self) -> None:
        pass

    def capabilities(self) -> object:  # pragma: no cover - nothing reads one here
        raise AssertionError("no capability is read here")

    def close(self) -> None:
        self.closed += 1


def a_driver(store: Store, built: list[ReportingMaster]) -> TurnDriver:
    def build(turn_id: str) -> MasterRuntime:
        master = ReportingMaster()
        built.append(master)
        runtime: MasterRuntime = master
        return runtime

    return TurnDriver(
        store=store,
        build_master=build,
        publish=lambda event: 0,
        withdraw_turn_approvals=lambda turn_id: 0,
        now=lambda: NOW,
    )


def run_one_turn(driver: TurnDriver, text: str) -> None:
    started = driver.send_turn(text)
    assert isinstance(started, TurnStarted), started
    assert driver.wait_for_turn(10.0), "the turn never ended"


# ----- 1. the writer works ----------------------------------------------------


def test_the_writer_persists_the_runtimes_own_conversation_id(store: Store) -> None:
    """D10's half that is built. Arrival before the value: the key is absent
    first, so what is read back is a change this turn made."""
    assert store.get_app_state(MASTER_SESSION_KEY) is None

    built: list[ReportingMaster] = []
    driver = a_driver(store, built)
    run_one_turn(driver, "hello")

    assert built, "no runtime was built"
    assert store.get_app_state(MASTER_SESSION_KEY) == RUNTIME_SESSION_ID, (
        "the persisted id is not the one the runtime reported"
    )


def test_the_first_event_that_names_a_session_wins(store: Store) -> None:
    """A later event restating a different id would move the conversation the
    next restart resumes — `_remember_session` takes the first, and this drives
    a runtime that reports two."""

    class Rambling(ReportingMaster):
        def send(self, text: str) -> AsyncIterator[MasterEvent]:
            async def stream() -> AsyncIterator[MasterEvent]:
                for value in (RUNTIME_SESSION_ID, "s6-a-second-id"):
                    yield MasterEvent(
                        kind="turn_started",
                        text=None,
                        tool_name=None,
                        payload={MASTER_SESSION_KEY: value},
                        occurred_at=NOW,
                    )

            return stream()

    driver = TurnDriver(
        store=store,
        build_master=lambda turn_id: Rambling(),
        publish=lambda event: 0,
        withdraw_turn_approvals=lambda turn_id: 0,
        now=lambda: NOW,
    )
    run_one_turn(driver, "hello")
    assert store.get_app_state(MASTER_SESSION_KEY) == RUNTIME_SESSION_ID


# ----- 2. the reader, measured --------------------------------------------------


def modules_that_call_resume(root: Path) -> frozenset[str]:
    """Every module under `root` holding a call of the form `<x>.resume(...)`.

    **The rule, written down** so a future reader can tell a narrowed scan from a
    changed tree: every `*.py` under `root` is parsed with `ast.parse`, and a
    module is in the set when it holds an `ast.Call` whose `func` is an
    `ast.Attribute` named `resume`. Attribute-named rather than type-resolved,
    for P-M4-21's reason: a type-directed scan goes quiet the moment a caller
    stops annotating its variable, which is the opposite of what a
    "does anything call this" check is for. The cost is that **any** `.resume(`
    in `src/` is reported, and that is the intended blast radius.
    """
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "resume"
            ):
                found.add(path.relative_to(root).as_posix())
    return frozenset(found)


#: Measured on this tree, not recalled: the one module in `src/` that calls
#: `.resume(`. The plan and the router's register both say there is none.
THE_ONLY_RESUME_CALLER = "daemons/plane.py"


def test_exactly_one_module_in_src_calls_resume(store: Store) -> None:
    """The plan's premise, measured — and it is false of this tree.

    Arrival before equality, P-M4-21's shape: the scan is asserted to have found
    *something* before it is asserted to have found only that. A set equality, so
    a **second** caller — the improvised-in-the-composition-root hole — is red
    too, and so is the caller vanishing again.
    """
    callers = modules_that_call_resume(SRC)
    assert callers, (
        "no module in src/ calls .resume() — the register's row has reopened,"
        " and D10's continuity is half-built again"
    )
    assert callers == frozenset({THE_ONLY_RESUME_CALLER}), sorted(callers)


def test_the_resume_scan_is_not_blind(store: Store) -> None:
    """The negative control, and it is what makes the emptiness above a fact.

    The scan is pointed at a tree that **does** contain a `.resume(` call, so a
    scan narrowed into uselessness — wrong attribute name, wrong glob, an
    `rglob` that stopped recursing — is caught before the equality above can
    pass vacuously.

    The fixture is **inert** (CLAUDE.md rule 1): `tests/qa/fixtures/` is not on
    an import path the suite executes, the module body performs no call at all,
    and the one call it exists for sits inside a function nobody invokes. It is
    read as text and parsed as an AST, never imported — the same treatment
    `tests/boundaries/fixtures/second_master_send_caller.py` gets from P-M4-21.
    """
    fixture = Path(__file__).parent / "fixtures" / "a_second_resume_caller.py"
    assert fixture.exists(), "S6's negative control fixture is missing"
    assert modules_that_call_resume(fixture.parent) == frozenset({fixture.name})


# ----- 3. the restart ---------------------------------------------------------


def test_a_restart_carries_the_persisted_conversation_into_the_new_runtime(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The chain, end to end, through the shipped `plane.build_master`.**

    Turn one writes the id through the shipped driver. Then a restart — a fresh
    `build_master` over the same store, which is all that crosses a `controld`
    restart — and the runtime it builds is asked to resume **that** id.

    `AgentSDKMaster` is replaced at `plane`'s own module seam by a recorder, for
    one reason: a real one would construct a vendor client behind a default-lane
    test. Everything between the store and that constructor is shipped code, and
    the recorder's constructor keywords are asserted to be the ones `build_master`
    really passes rather than absorbed by `**kwargs`.
    """
    run_one_turn(a_driver(store, []), "before the restart")
    persisted = store.get_app_state(MASTER_SESSION_KEY)
    assert persisted == RUNTIME_SESSION_ID

    built = _recording_master(monkeypatch)
    from shepherd.daemons import plane

    runtime = plane.build_master(store, "turn-after-the-restart")
    assert built, "build_master constructed no runtime"
    assert runtime is built[0]
    assert built[0].resumed == [persisted], (
        f"the new runtime resumed {built[0].resumed!r}, not the persisted"
        f" conversation {persisted!r}"
    )


def test_a_cold_start_resumes_nothing_rather_than_the_empty_string(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build_master`'s own sentence: *"a missing row resumes nothing"*.

    E-M4-8: an id the engine has no transcript for is a **lost** resume, not a
    cold start, so resuming `""` would turn every first boot into one. Arrival
    before absence — the test above shows the same code path resuming something.
    """
    assert store.get_app_state(MASTER_SESSION_KEY) is None
    built = _recording_master(monkeypatch)
    from shepherd.daemons import plane

    plane.build_master(store, "turn-cold")
    assert built and built[0].resumed == []

    # …and a row holding a non-string, which `app_state` can hold, is also
    # ignored rather than coerced into an id nobody chose.
    store.set_app_state(MASTER_SESSION_KEY, 7)
    plane.build_master(store, "turn-odd")
    assert built[1].resumed == [], "a non-string app_state row was resumed"


def _recording_master(monkeypatch: pytest.MonkeyPatch) -> list[ReportingMaster]:
    """Replace `plane.AgentSDKMaster` with a recorder, and keep what it is handed.

    The recorder takes the **named** keywords `build_master` passes, so a
    signature change there is a `TypeError` here rather than a silently absorbed
    argument — which is how a double stops testing the thing it stands for.
    """
    from shepherd.daemons import plane

    built: list[ReportingMaster] = []

    class Recorder(ReportingMaster):
        def __init__(
            self,
            *,
            caller_id: str,
            turn_id: object,
            bump: object,
            withdraw_turn_approvals: object,
            model: str,
        ) -> None:
            super().__init__()
            self.caller_id = caller_id
            self.model = model
            built.append(self)

    monkeypatch.setattr(plane, "AgentSDKMaster", Recorder)
    return built


def test_the_seam_declares_resume_on_both_implementations() -> None:
    """The other half of the honesty: the mechanism really is there.

    If `resume` were missing from the Protocol or from the shipped double, the
    finding would be *"the seam has no continuity member"*, which is a different
    and smaller defect. It is not — the member exists on the Protocol and on
    both peers, and only the caller is missing.
    """
    from shepherd.master.sdk_master import AgentSDKMaster
    from shepherd.testkit.scripted_master import ScriptedMaster

    assert hasattr(MasterRuntime, "resume")
    for implementation in (AgentSDKMaster, ScriptedMaster):
        assert callable(getattr(implementation, "resume", None)), implementation


def test_the_persisted_key_has_both_a_writer_and_a_reader(store: Store) -> None:
    """The key's two ends, counted by name over `src/`.

    Scanned on the **identifier**, never on its value: `MASTER_SESSION_KEY` is
    the one spelling both ends use (the driver's own docstring says why), and a
    scan for the string `"master_session_id"` would also match the runtime's
    payload key and the spec quotes in the docstrings.
    """
    writes, reads = 0, 0
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        writes += text.count("set_app_state(MASTER_SESSION_KEY")
        reads += text.count("get_app_state(MASTER_SESSION_KEY")
    assert writes >= 1, "nothing writes the key; the scan or the writer moved"
    assert reads >= 1, (
        "nothing reads master_session_id back out of app_state — the key is"
        " written on every turn and read on none, which is the gap the plan"
        " expected to find and this tree had already closed"
    )
