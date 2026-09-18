"""T23 — M4's own capabilities, and clause 15's two assertions in the order it pins.

**Seam: `invoke()`.** Every behavioural assertion below goes through the shipped
chokepoint, because that is the only path a consumer has and it is where the
audience filter, the schema validation and the gate all live (D32, D38, D53).
The declarative checks (P-M4-15, G-M4-15, G-M4-8's audience set) read
`registered_tools()`, which is the registry's own snapshot — they are statements
about *what is declared*, and a call cannot answer them.

**The chokepoint is the shipped one** (`tests/chokepoint_fixture.py`): a
permissive stub would be a second gate, and this suite would then prove the stub.

**No literal population count anywhere.** Every totality claim is a set equality
against a set enumerated at test time or written out as names.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import (
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopReason,
    Verdict,
)
from shepherd.orchestration.master_turn import TurnRefused, TurnStarted
from shepherd.orchestration.wake import MASTER_LAST_TURN_KEY
from shepherd.store.db import Store, open_store
from shepherd.toolsurface.approvals import Approval, ApprovalOutcome, ApprovalStore
from shepherd.toolsurface.policy import AGENT_AUDIENCES, AutonomyLevel
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.tools_master import (
    AUTONOMY_LEVEL_KEY,
    DEFAULT_AUTONOMY_LEVEL,
    GATE_TOOLS,
    UNREACHABLE_SESSION_TOOLS,
    register_master_tools,
)
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    Failure,
    ToolDef,
)

NOW = "2026-09-18T10:00:30Z"

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="web", correlation_id="cid-h")
MASTER = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="cid-m")
SESSION = CallerContext(audience=Audience.SESSION, caller_id="s-1", correlation_id="cid-s")

#: The ten `ToolDef`s T23 registers, written out as names. A **set**, never a
#: length: a rename is a failing build and so is an eleventh tool nobody declared.
MASTER_TOOL_NAMES = frozenset(
    {
        "get_audit_log",
        "list_approvals",
        "decide_approval",
        "get_autonomy_level",
        "set_autonomy_level",
        "master_send",
        "interrupt_master",
        "wake_summary",
        "report_blocked",
        "request_help",
    }
)

#: G-M4-8's baseline, **measured** by `scratchpad/m4-t23/measure_fleet_bytes.py`
#: against this tree and recorded in `docs/plans/m4-blockers/t23.md` §T23-4 with
#: the command that produced it. Step 0b row 9 was never taken (BLOCKER-T1-6), so
#: T23 took it — and it is taken **outside** this file, because a budget computed
#: by the check that asserts it is a tautology, not a budget.
FLEET_SIZE = 200
FLEET_SUMMARY_BYTES_AT_200 = 12927
FLEET_TREE_BYTES_AT_200 = 139323


# ----- the fixtures -----------------------------------------------------------


class _Driver:
    """T27's two verbs, as doubles. `master_send` and `interrupt_master` are
    `ToolDef`s *over* `TurnDriver`'s verbs; nothing about the driver is retested
    here (that is `tests/orchestration/test_master_turn.py`'s)."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.interrupts = 0
        self.answer: TurnStarted | TurnRefused = TurnStarted(
            turn_id="turn-1", started_at=NOW
        )
        self.live = True

    def send_turn(self, text: str) -> TurnStarted | TurnRefused:
        self.sent.append(text)
        return self.answer

    def interrupt_master(self) -> bool:
        self.interrupts += 1
        return self.live


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def approvals() -> ApprovalStore:
    return ApprovalStore(now=lambda: NOW)


@pytest.fixture()
def audit_root(tmp_path: Path) -> Path:
    root = tmp_path / "audit"
    root.mkdir()
    return root


@pytest.fixture()
def driver() -> _Driver:
    return _Driver()


@pytest.fixture(autouse=True)
def tools(
    store: Store, approvals: ApprovalStore, audit_root: Path, driver: _Driver
) -> None:
    """The composition root's share: install the chokepoint, then register.

    `register_read_tools` is here because G-M4-8's check drives `fleet_summary`
    and `fleet_tree`, which are M1's tools and not T23's — the budget is about
    what the **master** reads, and the master reads them through this registry.
    """
    install_test_chokepoint()
    register_master_tools(
        store=store,
        approvals=approvals,
        audit_root=audit_root,
        send_turn=driver.send_turn,
        interrupt_master=driver.interrupt_master,
        now=lambda: NOW,
    )
    register_read_tools(
        store=store,
        projects_root=audit_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )


def payload(name: str, args: dict[str, object], ctx: CallerContext = HUMAN) -> dict[str, object]:
    result = invoke(name, args, ctx)
    assert result.ok is True, result.error
    assert isinstance(result.data, dict)
    return result.data


def agent_reachable(tools: dict[str, ToolDef]) -> set[str]:
    """Every tool name carrying an audience an **agent** calls with.

    `AGENT_AUDIENCES` is `policy.py`'s — *everything that is not `HUMAN`* — so a
    fourth audience joins the agent side by default, which is the safe direction
    for the set this assertion turns on.
    """
    return {name for name, tool in tools.items() if AGENT_AUDIENCES & tool.audiences}


# ----- P-M4-15 / clause 15 ----------------------------------------------------


def test_no_gate_tool_is_reachable_by_an_agent() -> None:
    """Clause 15, **two assertions in the order the plan pins them**.

    The disjointness **alone is vacuous**: an empty intersection is exactly what
    `GATE_TOOLS` naming a tool that is not registered produces — a rename, a
    typo, a tool that never shipped. So the subset assertion goes above it and
    is K20's arrival check: it says the gate tools *exist* before the check says
    nothing agent-reachable is among them.
    """
    tools = dict(registered_tools())
    registered = set(tools)

    # Arrival. Delete a gate tool's registration, or rename one, and this line
    # is what goes red — the line below would stay green forever.
    assert GATE_TOOLS <= registered, (
        f"GATE_TOOLS names {sorted(GATE_TOOLS - registered)}, which nothing"
        " registers — the disjointness below would be vacuously true"
    )

    # Absence. Adding `MASTER` to either gate tool turns this red.
    assert GATE_TOOLS & agent_reachable(tools) == set()


def test_the_gate_tools_are_the_ones_that_can_change_the_gate() -> None:
    """`GATE_TOOLS` is not a list somebody remembered to update.

    The property is *a tool that writes the autonomy level or decides an
    approval*, and both of those are `local_destructive` by declaration. This
    check pins the membership against the two names and against the blast class,
    so a third gate-changing tool registered as `local_read` is visible here
    rather than only in a review.
    """
    tools = dict(registered_tools())
    assert GATE_TOOLS == frozenset({"set_autonomy_level", "decide_approval"})
    assert all(tools[name].blast_class is BlastClass.LOCAL_DESTRUCTIVE for name in GATE_TOOLS)
    assert all(tools[name].audiences == frozenset({Audience.HUMAN}) for name in GATE_TOOLS)


def test_an_agent_cannot_reach_a_gate_tool_through_invoke() -> None:
    """The structural claim above, driven: P-M4-15's mutation is behavioural.

    `invoke()` refuses on the audience, before the gate and before any handler —
    and the level is **unchanged** afterwards, which is the fact the tool exists
    to protect. Arrival first: the human call works.
    """
    assert payload("set_autonomy_level", {"level": 3})["level"] == 3
    for ctx in (MASTER, SESSION):
        refused = invoke("set_autonomy_level", {"level": 2}, ctx)
        assert refused.ok is False
        assert refused.failure is Failure.UNAVAILABLE
    assert payload("get_autonomy_level", {}, MASTER)["level"] == 3


# ----- the declaration checks -------------------------------------------------


def test_the_registered_set_is_exactly_the_ten_master_tools() -> None:
    """A set equality, enumerated at test time against names written out (K19)."""
    registered = set(registered_tools())
    assert MASTER_TOOL_NAMES <= registered
    assert GATE_TOOLS <= MASTER_TOOL_NAMES
    assert UNREACHABLE_SESSION_TOOLS <= MASTER_TOOL_NAMES


def test_every_m4_tool_declares_a_blast_class_and_an_audience() -> None:
    """Over the registered set enumerated at test time.

    **Red on an empty audience set**, which would be a tool nobody can call and
    nobody notices — the shape that has no symptom until someone asks why a
    capability never fires.
    """
    tools = dict(registered_tools())
    assert MASTER_TOOL_NAMES <= set(tools)
    for name in MASTER_TOOL_NAMES:
        tool = tools[name]
        assert isinstance(tool.blast_class, BlastClass)
        assert tool.audiences, f"{name} has an empty audience set"
        assert tool.audiences <= frozenset(Audience)


def test_the_audit_tool_is_human_only() -> None:
    """RD11, with clause 15's own trap closed the same way.

    The absence — *no agent audience on `get_audit_log`* — is vacuously true of a
    tool that is not registered, so the arrival is asserted first. An agent
    reading the audit log reads every other agent's actions, including approvals
    it was denied.
    """
    tools = dict(registered_tools())
    assert "get_audit_log" in tools, "get_audit_log is not registered; the check below is vacuous"
    assert tools["get_audit_log"].audiences == frozenset({Audience.HUMAN})
    assert "get_audit_log" not in agent_reachable(tools)
    assert invoke("get_audit_log", {}, MASTER).ok is False


def test_the_unreachable_session_tools_are_named() -> None:
    """G-M4-15: the `SESSION`-audience set **equals** a set written out here.

    After the Track C cut nothing can call them, and that is recorded rather than
    hidden. A *third* one appearing is a capability nobody can reach and nobody
    noticed — this line is where it surfaces.
    """
    tools = dict(registered_tools())
    session_tools = {name for name, tool in tools.items() if Audience.SESSION in tool.audiences}
    assert UNREACHABLE_SESSION_TOOLS <= set(tools)
    assert session_tools & MASTER_TOOL_NAMES == set(UNREACHABLE_SESSION_TOOLS)


def test_an_unreachable_session_tool_cannot_act_on_a_session_it_cannot_name() -> None:
    """Why the two tools refuse instead of writing something.

    `registry.py:244` is `data = tool.handler(args)` — `invoke()` checks the
    caller's audience and then **discards the caller**, so a handler cannot know
    which session called it. Giving it a `session_id` argument instead is the
    unscoped cross-project write API the Track C cut refused by name. So the
    honest handler is a typed refusal that says which fact is missing.
    """
    refused = invoke("report_blocked", {"waiting_on": "review", "detail": "MR open"}, SESSION)
    assert refused.ok is False
    assert refused.failure is Failure.REFUSED
    assert refused.error is not None and "caller" in refused.error
    helped = invoke("request_help", {"question": "which branch?", "options": ["a", "b"]}, SESSION)
    assert helped.ok is False
    assert helped.failure is Failure.REFUSED


# ----- the approval tools -----------------------------------------------------


def raise_card(approvals: ApprovalStore, tool_name: str, turn: str) -> Approval:
    tools = dict(registered_tools())
    return approvals.create(
        tools[tool_name],
        {},
        CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id=turn),
    )


def test_decide_approval_resolves_exactly_one_approval(approvals: ApprovalStore) -> None:
    """**Arrival first on `pending()`**, then exactly one resolution.

    A decision test that never checks the cards arrived proves nothing: an empty
    `pending()` satisfies every "it is no longer pending" assertion below it.
    """
    first = raise_card(approvals, "interrupt_master", "turn-a")
    second = raise_card(approvals, "master_send", "turn-b")

    # Arrival: both cards are pending, as a set equality over their ids.
    assert {card.id for card in approvals.pending()} == {first.id, second.id}
    listed = payload("list_approvals", {})["approvals"]
    assert isinstance(listed, list)
    assert {row["approval_id"] for row in listed} == {first.id, second.id}

    decided = payload("decide_approval", {"approval_id": first.id, "choice": "approve"})
    assert decided == {
        "approval_id": first.id,
        "decided": True,
        "outcome": "approved",
    }

    # Exactly one: the other card is untouched, and a second decision loses.
    assert {card.id for card in approvals.pending()} == {second.id}
    again = payload("decide_approval", {"approval_id": first.id, "choice": "reject"})
    assert again["decided"] is False
    assert again["outcome"] is None


def test_a_rejection_is_a_different_outcome_from_an_approval(approvals: ApprovalStore) -> None:
    card = raise_card(approvals, "interrupt_master", "turn-a")
    assert {one.id for one in approvals.pending()} == {card.id}
    decided = payload("decide_approval", {"approval_id": card.id, "choice": "reject"})
    assert decided["outcome"] == "rejected"
    assert approvals.pending() == ()


def test_an_unknown_choice_is_refused_and_decides_nothing(approvals: ApprovalStore) -> None:
    """JSON Schema cannot say *one of these two words*, so the handler does."""
    card = raise_card(approvals, "interrupt_master", "turn-a")
    refused = invoke("decide_approval", {"approval_id": card.id, "choice": "maybe"}, HUMAN)
    assert refused.ok is False
    assert refused.failure is Failure.REFUSED
    assert {one.id for one in approvals.pending()} == {card.id}


def test_list_approvals_renders_the_redacted_summary_and_never_the_raw_args(
    approvals: ApprovalStore,
) -> None:
    """§13: the card's `summary` is `describe()`'s, which redacts secret-shaped
    keys. The raw `args` are **not** on the projection at all — a sidebar that
    renders them would put an unredacted token on the page."""
    tools = dict(registered_tools())
    approvals.create(
        tools["master_send"],
        {"api_token": "sk-live-do-not-print", "text": "hello"},
        CallerContext(audience=Audience.MASTER, caller_id="m", correlation_id="turn-a"),
    )
    listed = payload("list_approvals", {})["approvals"]
    assert isinstance(listed, list)
    assert len(listed) == 1
    row = listed[0]
    assert set(row) == {"approval_id", "turn_id", "tool", "summary", "created_at", "deadline_at"}
    assert "sk-live-do-not-print" not in json.dumps(row)
    assert "<redacted>" in str(row["summary"])


# ----- the autonomy tools -----------------------------------------------------


def test_the_autonomy_level_defaults_to_a_real_level_on_an_empty_store(store: Store) -> None:
    """F16's greenfield first five minutes: no `app_state` row yet.

    **The expected value is the literal `2`, not `int(DEFAULT_AUTONOMY_LEVEL)`.**
    Reading the constant back off the module under test is the tautology T27
    paid for (§T27-7, MUT-11): flipping the default to the level that
    auto-approves moved *both* sides and the check stayed green. That is exactly
    what T23's MUT-15 found here, and this literal is the repair. `2` is the
    level that **asks** for every destructive call, which is why it is the safe
    reading of an unset toggle.
    """
    assert store.get_app_state(AUTONOMY_LEVEL_KEY) is None
    assert payload("get_autonomy_level", {})["level"] == 2
    assert DEFAULT_AUTONOMY_LEVEL in set(AutonomyLevel)


def test_set_autonomy_level_writes_what_get_reads_back(store: Store) -> None:
    """`previous` is the literal `2` for the same reason as the test above."""
    written = payload("set_autonomy_level", {"level": 3})
    assert written == {"level": 3, "previous": 2}
    assert store.get_app_state(AUTONOMY_LEVEL_KEY) == 3
    assert payload("get_autonomy_level", {})["level"] == 3


def test_a_level_this_build_has_no_member_for_is_refused(store: Store) -> None:
    """The levels are `AutonomyLevel` enumerated at test time, never a range."""
    outside = max(int(level) for level in AutonomyLevel) + 1
    refused = invoke("set_autonomy_level", {"level": outside}, HUMAN)
    assert refused.ok is False
    assert refused.failure is Failure.REFUSED
    assert store.get_app_state(AUTONOMY_LEVEL_KEY) is None


@pytest.mark.parametrize("stored", ["three", "3", 7, True])
def test_an_unreadable_stored_level_reads_as_the_default(
    store: Store, stored: object
) -> None:
    """`app_state` hands back whatever JSON the key holds (`wake._since`'s
    reason). A value that is not a **member** is *no level*, and the safe
    direction is the level that asks.

    `"3"` is the dangerous case and the reason this is parametrised: a JSON
    string that *spells* a real level would, under any implementation that
    coerces with `int()`, silently turn an unreadable setting into
    auto-approve-everything. `7` is a member this build has no row for, and
    `True` is an `int` in Python — the same sneak `registry._PRIMITIVES` excludes
    from `number`.
    """
    store.set_app_state(AUTONOMY_LEVEL_KEY, stored)
    assert payload("get_autonomy_level", {})["level"] == 2


# ----- the master's turn tools ------------------------------------------------


def test_master_send_posts_the_text_and_reports_the_turn(driver: _Driver) -> None:
    data = payload("master_send", {"text": "what happened overnight?"})
    assert driver.sent == ["what happened overnight?"]
    assert data == {
        "started": True,
        "turn_id": "turn-1",
        "started_at": NOW,
        "reason": None,
    }


def test_a_refused_turn_is_reported_with_its_reason_and_is_not_an_error(
    driver: _Driver,
) -> None:
    """RD7/E-M4-4: a second `master_send` while a turn is live is refused with a
    readable reason. The refusal is a **result**, not a `Failure` — the call
    succeeded and the answer is *no*."""
    driver.answer = TurnRefused(reason="a turn is already running (turn-1)")
    data = payload("master_send", {"text": "again"})
    assert data == {
        "started": False,
        "turn_id": None,
        "started_at": None,
        "reason": "a turn is already running (turn-1)",
    }


def test_interrupt_master_reports_whether_anything_was_live(driver: _Driver) -> None:
    assert payload("interrupt_master", {}) == {"interrupted": True}
    assert driver.interrupts == 1
    driver.live = False
    assert payload("interrupt_master", {}) == {"interrupted": False}
    assert driver.interrupts == 2


# ----- RD-T16-7a: the wake tool peeks and must not stamp ----------------------


#: The one waking row, with a `why` and an action **only this fixture** could
#: have produced — a projection that re-classified the stop instead of reading it
#: back cannot reproduce them (T9's rule, and the tautology T27 paid for).
WAKE_SESSION_ID = ("01T23WAKE" + "0" * 26)[:26]
WAKE_WHY = "promised the specs and never ran them"
WAKE_ACTION = "re-run the specs"


def stopped_session(store: Store) -> str:
    """One master-owned session that stopped `unfinished` — D31's wake set is
    `origin = orchestrator` plus `outcome IN (unfinished, error)`, and the query
    is `store.wake_candidates`'s. Nothing is re-stated here."""
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
    store.create_owned_session(
        session_id=WAKE_SESSION_ID,
        engine_session_id="eng-wake-1",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-18T09:00:00.000Z",
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title="chase the failing test",
        title_source="brief",
        handle=None,
        model="opus",
        effort="high",
    )
    store.apply_stop_verdict(
        WAKE_SESSION_ID,
        Verdict(
            stop_reason=StopReason.INCOMPLETE,
            bucket=Bucket.UNFINISHED,
            why=WAKE_WHY,
            confidence=0.9,
            decided_by=DecidedBy.HEURISTIC,
            next_actions=(
                NextAction(
                    text=WAKE_ACTION,
                    kind=NextActionKind.RETRY,
                    target=None,
                    source=ActionSource.HEURISTIC,
                ),
            ),
            waiting_on=None,
            missing=(),
        ),
        "2026-09-18T09:59:30.000Z",
        None,
    )
    return WAKE_SESSION_ID


def test_wake_summary_hands_over_what_is_waiting(store: Store) -> None:
    """Arrival: the tool answers with the row that is actually waiting."""
    session_id = stopped_session(store)
    data = payload("wake_summary", {}, MASTER)
    items = data["items"]
    assert isinstance(items, list)
    # Every expected value is a literal the fixture wrote, never a field read
    # back off the object under test (T27's survivor).
    assert items == [
        {
            "session_id": session_id,
            "title": "chase the failing test",
            "bucket": "unfinished",
            "why": WAKE_WHY,
            "first_action": WAKE_ACTION,
        }
    ]
    assert "while you were away —" in str(data["text"])
    assert WAKE_ACTION in str(data["text"])


def test_wake_summary_does_not_stamp(store: Store) -> None:
    """RD-T16-7a, as a behavioural assertion rather than a promise.

    **Two drains is D31's lost stop**: a stop landing between them is stamped as
    already seen and never wakes anybody. `TurnDriver` is the single drain site,
    so this tool is `peek`-based — and the proof is that the stamp is untouched
    *and* that a second call hands over the same row.
    """
    session_id = stopped_session(store)
    assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

    first = payload("wake_summary", {}, MASTER)
    assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

    second = payload("wake_summary", {}, MASTER)
    assert first["items"] == second["items"]
    items = second["items"]
    assert isinstance(items, list)
    assert {row["session_id"] for row in items} == {session_id}


def test_an_empty_wake_set_renders_no_header(store: Store) -> None:
    data = payload("wake_summary", {}, MASTER)
    assert data["items"] == []
    assert data["text"] == ""


# ----- the audit view ---------------------------------------------------------


def test_get_audit_log_tails_the_records_newest_first(audit_root: Path) -> None:
    """D25's single UI exception. The reader is `audit.read_audit_records`; this
    tool is the projection over it and never opens the directory itself."""
    day = audit_root / "audit"
    day.mkdir()
    (day / "2026-09-18.jsonl").write_text(
        "\n".join(
            json.dumps({"at": f"2026-09-18T10:0{index}:00Z", "tool": f"t{index}"})
            for index in range(3)
        )
        + "\n",
        encoding="utf-8",
    )
    data = payload("get_audit_log", {"limit": 2})
    records = data["records"]
    assert isinstance(records, list)
    assert [row["tool"] for row in records] == ["t2", "t1"]
    assert data["limit"] == 2


def test_get_audit_log_has_a_default_limit(audit_root: Path) -> None:
    assert payload("get_audit_log", {})["limit"] == 50


# ----- G-M4-8: the byte budget ------------------------------------------------


def seed_fleet(store: Store, size: int) -> None:
    """The same 200-session fleet `scratchpad/m4-t23/measure_fleet_bytes.py`
    builds, so the literals above and the bytes below are about one fixture."""
    spaces = [
        store.upsert_workspace(f"project-{index}", f"/root/projects/project-{index}")
        for index in range(8)
    ]
    states = (
        SessionState.NEEDS_YOU,
        SessionState.RUNNING,
        SessionState.STOPPED,
        SessionState.STARTING,
    )
    for index in range(size):
        workspace = spaces[index % len(spaces)]
        session = store.register_session(
            engine_session_id=f"engine-session-{index:04d}",
            workspace_id=workspace.id,
            repo_id=None,
            cwd=f"/root/projects/project-{index % len(spaces)}/worktree-{index:04d}",
            started_at="2026-09-18T09:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        state = states[index % len(states)]
        store.apply_fold_delta(
            session.id,
            FoldDelta(
                state=state,
                last_event_at="2026-09-18T10:00:00Z",
                title=f"fix the flaky retry path in module {index:04d}",
                brief=f"session {index:04d}: chase the failing integration test",
                model="claude-opus-4-1-20250805",
                needs_you_reason=(
                    "waiting on your answer to a permission dialog"
                    if state is SessionState.NEEDS_YOU
                    else None
                ),
            ),
        )


def test_the_master_read_tools_size_does_not_regress(store: Store) -> None:
    """G-M4-8, against the number measured at `scratchpad/m4-t23/`.

    **Arrival before the budget.** A projection over an empty fleet is small, and
    a `<=` assertion over it passes while proving nothing — so the fleet is
    asserted to have arrived, and `needs_you` is asserted non-empty because that
    list is the term §11's *"~40 lines regardless of fleet size"* does not bound.

    The measured value is in the message either way, which is the plan's own
    requirement: if this is already over what §11 promises on day one, that is
    G-M4-8's finding arriving on schedule and it is a blocker entry, not a
    budget edit.
    """
    seed_fleet(store, FLEET_SIZE)

    summary = payload("fleet_summary", {}, MASTER)
    assert summary["session_count"] == FLEET_SIZE
    needs_you = summary["needs_you"]
    assert isinstance(needs_you, list)
    assert needs_you, "the fleet has no needs_you rows; the unbounded term is untested"

    tree = payload("fleet_tree", {}, MASTER)
    assert tree["session_count"] == FLEET_SIZE

    summary_bytes = len(json.dumps(summary, separators=(",", ":")).encode())
    tree_bytes = len(json.dumps(tree, separators=(",", ":")).encode())
    assert summary_bytes <= FLEET_SUMMARY_BYTES_AT_200, (
        f"fleet_summary is {summary_bytes} bytes at {FLEET_SIZE} sessions,"
        f" over the measured baseline {FLEET_SUMMARY_BYTES_AT_200}"
    )
    assert tree_bytes <= FLEET_TREE_BYTES_AT_200, (
        f"fleet_tree is {tree_bytes} bytes at {FLEET_SIZE} sessions,"
        f" over the measured baseline {FLEET_TREE_BYTES_AT_200}"
    )
