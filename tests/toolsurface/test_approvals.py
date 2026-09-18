"""T4 — the approval store, the block, and D54's withdrawal.

Every emptiness below is preceded by an **arrival**, and every arrival is
proved by its own mutation (§T3-4's rule: an arrival nobody has mutated is an
arrival nobody has proved). The mutation ledger is in
`docs/plans/m4-blockers/t4.md`.

**The trap this file is written against.** Every approval assertion here would
pass against an `await_decision` that returns immediately — a pending card, a
recorded outcome, a bumped counter are all true of a store that never blocks.
So the blocking checks assert a **synchronisation, not a sample**: the worker
sets a `threading.Event` *after* `await_decision` returns, and the test asserts
that Event is **unset** while the card is pending, before deciding anything.
`Thread.is_alive()` after `start()` is true whether or not the call began.
"""

from __future__ import annotations

import ast
import itertools
import threading
from datetime import timedelta
from pathlib import Path
from collections.abc import Callable, Sequence

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import parse_stamp
from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.approvals import (
    APPROVAL_CREATED_KIND,
    APPROVAL_DECIDED_KIND,
    TIMED_OUT_TEXT,
    WITHDRAWN_TEXT,
    Approval,
    ApprovalOutcome,
    ApprovalStore,
    build_authorizer,
    describe,
)
from shepherd.toolsurface.approvals import _ANSWERS, REDACTED, SECRET_KEY_MARKERS
from shepherd.toolsurface.export import DENIED_TEXT
from shepherd.toolsurface.policy import (
    AGENT_AUDIENCES,
    APPROVAL_TIMEOUT_S,
    ApprovedBy,
    AutonomyLevel,
    Verdict,
    decide,
)
from shepherd.toolsurface.types import (
    Audience,
    AuthzOutcome,
    Authorizer,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolDef,
)

#: A stamp the injected clock hands back. One value, so `created_at` is a fact
#: about the clock rather than about how long the test took.
FIXED_NOW = "2026-09-17T12:00:00.000Z"


def a_clock(stamps: Sequence[str] = (FIXED_NOW,)) -> Callable[[], str]:
    values = iter(stamps)
    last = stamps[-1]

    def now() -> str:
        return next(values, last)

    return now


def a_monotonic(ticks: Sequence[float]) -> Callable[[], float]:
    """A fake `time.monotonic`. The last value repeats, so a mutant that reads
    the clock a different number of times still terminates."""
    values = iter(ticks)
    last = ticks[-1]

    def monotonic() -> float:
        return next(values, last)

    return monotonic


def a_tool(
    name: str = "kill_session",
    blast_class: BlastClass = BlastClass.LOCAL_DESTRUCTIVE,
    description: str = "Stop a session and leave its transcript in place.",
) -> ToolDef:
    return ToolDef(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
        blast_class=blast_class,
        handler=lambda args, ctx: None,
        audiences=frozenset(Audience),
    )


def a_context(
    audience: Audience = Audience.MASTER, correlation_id: str = "turn-1"
) -> CallerContext:
    return CallerContext(
        audience=audience, caller_id="master", correlation_id=correlation_id
    )


def a_store(
    now: Callable[[], str] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> ApprovalStore:
    if monotonic is None:
        return ApprovalStore(now=now or a_clock())
    return ApprovalStore(now=now or a_clock(), monotonic=monotonic)


def create_one(store: ApprovalStore, **kwargs: object) -> Approval:
    tool = a_tool()
    args: ToolArgs = {"session_id": "s1"}
    ctx = a_context(**kwargs)  # type: ignore[arg-type]
    return store.create(tool, args, ctx)


# ----- P-M4-10: exactly one terminal outcome --------------------------------


def test_an_approval_has_exactly_one_terminal_outcome() -> None:
    """Every ordered pair of outcomes, enumerated from the enum at test time.

    Never a literal count: the pairs are `product(set(ApprovalOutcome),
    set(ApprovalOutcome))`, so a fifth outcome joins the drive by existing.
    """
    outcomes = set(ApprovalOutcome)
    pairs = list(itertools.product(outcomes, outcomes))
    # Arrival before the property: an empty product makes every assertion in
    # the loop below vacuously true.
    assert pairs, "the outcome product is empty; the loop below proves nothing"
    assert len(pairs) == len(outcomes) ** 2

    for first, second in pairs:
        store = a_store()
        approval = create_one(store)
        assert store.decide(approval.id, first) is True, (first, second)
        assert store.decide(approval.id, second) is False, (first, second)
        # The first outcome stands, read back through the public seam.
        assert store.await_decision(approval.id, timeout_s=0.0) is first


# ----- K20: the block is a synchronisation, not a sample --------------------


class _Caller:
    """A worker that calls `await_decision` and reports **after** it returns.

    `entered` is set immediately before the call, so the negative assertion
    below is *absence after a confirmed entry* rather than a race with thread
    start-up. `returned` is set **after** the call returns — which is the whole
    of the K20 discipline: asserting `thread.is_alive()` is true whether or not
    `await_decision` ever blocked.
    """

    def __init__(self, store: ApprovalStore, approval_id: str, timeout_s: float) -> None:
        self.entered = threading.Event()
        self.returned = threading.Event()
        self.outcomes: list[ApprovalOutcome] = []
        self._store = store
        self._approval_id = approval_id
        self._timeout_s = timeout_s
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self.entered.set()
        outcome = self._store.await_decision(self._approval_id, self._timeout_s)
        self.outcomes.append(outcome)
        self.returned.set()

    def start(self) -> None:
        self.thread.start()
        assert self.entered.wait(WAIT_S), "the worker never reached await_decision"

    def join(self) -> None:
        self.thread.join(WAIT_S)
        assert not self.thread.is_alive(), "the worker was never released"


#: How long a positive assertion may wait for a release. Generous: it bounds a
#: hang, it does not time anything.
WAIT_S = 5.0

#: How long a **negative** assertion watches for an event that must not arrive.
#: An `await_decision` that returns immediately sets `returned` in microseconds.
NOT_YET_S = 0.25


def test_a_blocked_caller_is_released_by_a_decision() -> None:
    store = a_store()
    approval = create_one(store)
    caller = _Caller(store, approval.id, timeout_s=WAIT_S * 10)
    caller.start()

    # Arrival first (K20): the card exists and is pending…
    assert [pending.id for pending in store.pending()] == [approval.id]
    # …and the caller has **not** returned. This is the assertion the whole
    # file rests on: it goes red against an `await_decision` that returns
    # immediately, which is the mutation that makes every other check vacuous.
    assert not caller.returned.wait(NOT_YET_S), "await_decision did not block"
    assert caller.outcomes == []
    assert [pending.id for pending in store.pending()] == [approval.id]

    assert store.decide(approval.id, ApprovalOutcome.APPROVED) is True

    assert caller.returned.wait(WAIT_S), "the decision never released the caller"
    caller.join()
    assert caller.outcomes == [ApprovalOutcome.APPROVED]
    assert store.pending() == ()


# ----- the authorizer: §11's `authorize()` around T3's gate -----------------


class _Recorder:
    """The two injected side effects, recorded rather than mocked away."""

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []
        self.bumps: list[AnomalyKind] = []

    def publish(self, event: StreamEvent) -> int:
        self.events.append(event)
        return len(self.events)

    def bump(self, kind: AnomalyKind) -> None:
        self.bumps.append(kind)

    def kinds(self) -> list[str]:
        return [event.kind for event in self.events]


def an_authorizer(
    store: ApprovalStore,
    recorder: _Recorder,
    level: AutonomyLevel = AutonomyLevel.LEVEL_2,
) -> Authorizer:
    return build_authorizer(
        store=store,
        level=lambda: level,
        publish=recorder.publish,
        bump=recorder.bump,
        now=a_clock(),
    )


def test_an_unanswered_approval_times_out_and_counts() -> None:
    """The 600 s deadline, asserted in milliseconds through the injected clock.

    `monotonic` hands back `0.0` and then `APPROVAL_TIMEOUT_S`, so the caller's
    own deadline has passed the first time it is consulted and no wall-clock
    second is spent proving a ten-minute timeout.
    """
    recorder = _Recorder()
    store = a_store(monotonic=a_monotonic([0.0, APPROVAL_TIMEOUT_S]))
    authorize = an_authorizer(store, recorder)

    outcome = authorize(a_tool(), {"session_id": "s1"}, a_context())

    assert outcome == AuthzOutcome(
        allowed=False,
        approved_by=ApprovedBy.TIMEOUT,
        approval_id=outcome.approval_id,
        reason=TIMED_OUT_TEXT,
    )
    assert outcome.approval_id is not None
    assert recorder.bumps == [AnomalyKind.APPROVAL_TIMED_OUT]
    assert recorder.kinds() == [APPROVAL_CREATED_KIND, APPROVAL_DECIDED_KIND]
    # Resolved, never left pending — and readable as `timed_out` afterwards.
    assert store.pending() == ()
    assert store.await_decision(outcome.approval_id, timeout_s=0.0) is (
        ApprovalOutcome.TIMED_OUT
    )


# ----- D54: withdrawal resolves, it never deletes ----------------------------


def test_a_withdrawn_approval_is_denied_and_never_left_pending() -> None:
    store = a_store()
    approval = create_one(store)
    # Arrival first: the card is pending, and its deadline is genuinely in the
    # future — `APPROVAL_TIMEOUT_S` past its creation, not the same instant.
    # Without this, "withdrawn" and "timed out" would be indistinguishable
    # (D54's whole reason, and P-M4-22's).
    assert [pending.id for pending in store.pending()] == [approval.id]
    created = parse_stamp(approval.created_at)
    deadline = parse_stamp(approval.deadline_at)
    assert created is not None and deadline is not None
    assert deadline - created == timedelta(seconds=APPROVAL_TIMEOUT_S)

    caller = _Caller(store, approval.id, timeout_s=WAIT_S * 10)
    caller.start()
    assert not caller.returned.wait(NOT_YET_S), "await_decision did not block"

    assert store.withdraw(approval.id) is True
    assert caller.returned.wait(WAIT_S), "the withdrawal never released the caller"
    caller.join()
    assert caller.outcomes == [ApprovalOutcome.WITHDRAWN]

    # Resolved, not deleted: it is gone from `pending()` **and** still
    # answerable. A deleted approval is indistinguishable from one that never
    # existed, which is what the `KeyError` below shows an unknown id doing.
    assert store.pending() == ()
    assert store.await_decision(approval.id, timeout_s=0.0) is ApprovalOutcome.WITHDRAWN
    with pytest.raises(KeyError):
        store.await_decision("no-such-approval", timeout_s=0.0)

    # E-M4-2: a decision after a withdrawal is refused, and the reason the
    # agent reads is the withdrawal's.
    assert store.decide(approval.id, ApprovalOutcome.APPROVED) is False


def test_withdraw_all_resolves_every_pending_approval_of_one_turn() -> None:
    store = a_store()
    mine = [create_one(store, correlation_id="turn-A") for _ in range(3)]
    theirs = [create_one(store, correlation_id="turn-B") for _ in range(2)]
    # Arrival first, as sets of ids rather than counts.
    assert {pending.id for pending in store.pending()} == {
        approval.id for approval in mine + theirs
    }

    # Clause 20: a thread blocked in `Condition.wait` does not notice a daemon
    # stopping, so shutdown's release path is asserted on a real blocked caller
    # rather than on the return value alone. P2 measured that `interrupt()`
    # never reaches a running handler, so this is the **only** thing that can
    # free it.
    caller = _Caller(store, mine[0].id, timeout_s=WAIT_S * 10)
    caller.start()
    assert not caller.returned.wait(NOT_YET_S), "await_decision did not block"

    assert store.withdraw_all("turn-A") == len(mine)
    assert caller.returned.wait(WAIT_S), "withdraw_all never released the caller"
    caller.join()
    assert caller.outcomes == [ApprovalOutcome.WITHDRAWN]

    # Another turn's approvals are untouched…
    assert {pending.id for pending in store.pending()} == {
        approval.id for approval in theirs
    }
    # …and this turn's are resolved rather than deleted.
    for approval in mine:
        assert (
            store.await_decision(approval.id, timeout_s=0.0)
            is ApprovalOutcome.WITHDRAWN
        )
    # A second withdrawal of the same turn resolves nothing: they are terminal.
    assert store.withdraw_all("turn-A") == 0


# ----- DP2, both halves, enumerated at test time ----------------------------


def test_no_human_call_ever_creates_an_approval() -> None:
    classes = set(BlastClass)
    assert classes, "BlastClass enumerated empty; the loop below proves nothing"
    recorder = _Recorder()
    # The deadline has passed the first time it is consulted, so if the audience
    # check is inverted and a card **is** raised, this test **fails** rather
    # than blocking forever on a card nobody will answer. A mutant whose verdict
    # the suite cannot deliver is a mutant nobody has proved (MUT-14).
    store = a_store(monotonic=a_monotonic([0.0, APPROVAL_TIMEOUT_S]))
    authorize = an_authorizer(store, recorder)

    for blast_class in classes:
        outcome = authorize(
            a_tool(blast_class=blast_class), {"session_id": "s1"},
            a_context(audience=Audience.HUMAN),
        )
        assert outcome.allowed is True, blast_class
        assert outcome.approval_id is None, blast_class

    assert store.pending() == ()
    assert recorder.events == []
    assert recorder.bumps == []


def test_every_master_destructive_call_creates_exactly_one_approval() -> None:
    """DP2's other half — the one a do-nothing authorizer does **not** satisfy.

    The expectation is not a written-out list of classes: it is every
    `(class, audience)` pair the **shipped gate** answers `ASK` for, enumerated
    from `set(BlastClass)` and `AGENT_AUDIENCES` at test time. Two arrivals
    guard it — the pair set is non-empty, and it contains the pair §11's table
    is written about — so it cannot pass by enumerating nothing.
    """
    audiences = AGENT_AUDIENCES
    classes = set(BlastClass)
    assert classes and audiences
    level = AutonomyLevel.LEVEL_2
    asked = {
        (blast_class, audience)
        for blast_class in classes
        for audience in audiences
        if decide(blast_class, level, audience).verdict is Verdict.ASK
    }
    assert (BlastClass.LOCAL_DESTRUCTIVE, Audience.MASTER) in asked
    allowed = {
        (blast_class, audience)
        for blast_class in classes
        for audience in audiences
    } - asked
    assert allowed, "no allow pair to contrast against"

    carded: set[tuple[BlastClass, Audience]] = set()
    for blast_class in sorted(classes):
        for audience in sorted(audiences):
            recorder = _Recorder()
            # The deadline has passed the first time it is consulted, so an
            # unanswered card resolves without a wall-clock wait.
            store = a_store(monotonic=a_monotonic([0.0, APPROVAL_TIMEOUT_S]))
            authorize = an_authorizer(store, recorder, level=level)
            outcome = authorize(
                a_tool(blast_class=blast_class),
                {"session_id": "s1"},
                a_context(audience=audience),
            )
            created = [
                event for event in recorder.events
                if event.kind == APPROVAL_CREATED_KIND
            ]
            if outcome.approval_id is not None:
                carded.add((blast_class, audience))
                # Exactly one card, and it is the one the outcome names.
                assert [event.payload["approval_id"] for event in created] == [
                    outcome.approval_id
                ], (blast_class, audience)
                assert outcome.allowed is False, (blast_class, audience)
            else:
                assert created == [], (blast_class, audience)
                assert outcome.allowed is True, (blast_class, audience)

    assert carded == asked


# ----- the card summary is derived, never tabulated -------------------------

APPROVALS_SOURCE = Path("src/shepherd/toolsurface/approvals.py").resolve()


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(APPROVALS_SOURCE.read_text(encoding="utf-8"))
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(found) == 1, f"{name} is not defined exactly once in {APPROVALS_SOURCE}"
    return found[0]


def test_the_card_summary_is_derived_from_the_tool_def() -> None:
    first = a_tool(name="kill_session", description="Stop a session.")
    second = a_tool(name="delete_workspace", description="Remove a workspace.")

    assert describe(first, {}) == "Stop a session."
    assert describe(second, {}) == "Remove a workspace."
    # A tool this build has never heard of still gets a summary — which a
    # per-tool sentence table could not produce.
    unknown = a_tool(name="a_tool_no_table_knows", description="Do a new thing.")
    assert describe(unknown, {"session_id": "s1"}) == "Do a new thing. (session_id=s1)"
    # The argument mapping is the tool's own arguments, sorted, all of them.
    assert describe(first, {"b": 2, "a": 1}) == "Stop a session. (a=1, b=2)"
    # …redacted (§13): the key is readable, the secret is not.
    summary = describe(first, {"api_token": "ghp_realsecret", "session_id": "s1"})
    assert "ghp_realsecret" not in summary
    assert "api_token" in summary and "session_id=s1" in summary

    # And structurally: no per-tool sentence table may appear in `describe`.
    # A behavioural check alone would pass against a table plus a fallback.
    body = _function("describe")
    literals = [node for node in ast.walk(body) if isinstance(node, (ast.Dict, ast.Set))]
    assert literals == [], "describe() grew a table; §11's summary is derived"
    constants = {
        node.value
        for node in ast.walk(body)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not any(
        "session" in text or "workspace" in text for text in constants
    ), constants


def test_the_denial_text_has_exactly_one_spelling_in_the_tree() -> None:
    """RD-T11-2. `export.py` declares the wording; this module produces the
    denial. Two spellings of a user-facing refusal is a defect no test in
    either file would catch, so the check is over the whole of `src/`."""
    assert _ANSWERS[ApprovalOutcome.REJECTED][2] is DENIED_TEXT
    sources = sorted(Path("src").rglob("*.py"))
    assert sources, "the source scan found no files at all"
    spellers = [
        path
        for path in sources
        if f'"{DENIED_TEXT}"' in path.read_text(encoding="utf-8")
    ]
    assert [path.name for path in spellers] == ["export.py"], spellers


# ----- P-M4-10 under real contention ----------------------------------------


def test_the_compare_and_set_survives_real_contention() -> None:
    """One terminal outcome when every outcome is attempted at once.

    The sequential pair drive above cannot tell a compare-and-set from a
    check-then-set with a window in it. Here one thread per outcome —
    enumerated, never a literal count — is released by a `Barrier` onto the
    same approval, over enough rounds that a lost update would show.
    """
    outcomes = sorted(set(ApprovalOutcome))
    assert outcomes
    store = a_store()
    rounds = 200

    for _ in range(rounds):
        approval = create_one(store)
        barrier = threading.Barrier(len(outcomes))
        winners: list[ApprovalOutcome] = []
        guard = threading.Lock()

        def attempt(outcome: ApprovalOutcome) -> None:
            barrier.wait(WAIT_S)
            if store.decide(approval.id, outcome):
                with guard:
                    winners.append(outcome)

        threads = [
            threading.Thread(target=attempt, args=(outcome,), daemon=True)
            for outcome in outcomes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT_S)
            assert not thread.is_alive()

        assert len(winners) == 1, winners
        assert store.await_decision(approval.id, timeout_s=0.0) is winners[0]
        assert approval.id not in {p.id for p in store.pending()}


def test_every_outcome_has_an_answer() -> None:
    """§T3-1's shape: the answer table is a second statement of the outcome
    enum, compared as a **set**. A fifth outcome is then a failing test rather
    than a `KeyError` in production, or — worse — a fall-through to allow."""
    domain = set(ApprovalOutcome)
    assert domain, "the outcome enum is empty; the comparison below is vacuous"
    assert set(_ANSWERS) == domain
    # And exactly one answer allows the call.
    allowing = {outcome for outcome, answer in _ANSWERS.items() if answer[0]}
    assert allowing == {ApprovalOutcome.APPROVED}
    # `USER` is produced here and nowhere else (K23, §T3-3).
    attributions = {answer[1] for answer in _ANSWERS.values()}
    assert ApprovedBy.USER in attributions
    assert _ANSWERS[ApprovalOutcome.APPROVED][1] is ApprovedBy.USER


def test_a_withdrawal_denies_the_blocked_call_and_counts() -> None:
    """D54 end to end, through the authorizer seam the master actually uses.

    This is the path P2 makes load-bearing: `interrupt()` never reaches the
    running handler, so the only thing that can free this thread is the
    withdrawal below.
    """
    recorder = _Recorder()
    store = a_store()
    authorize = an_authorizer(store, recorder)
    entered, returned = threading.Event(), threading.Event()
    answers: list[AuthzOutcome] = []

    def call() -> None:
        entered.set()
        answers.append(authorize(a_tool(), {"session_id": "s1"}, a_context()))
        returned.set()

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    assert entered.wait(WAIT_S)
    # Arrival: one card, pending, with its deadline still in the future…
    assert not returned.wait(NOT_YET_S), "authorize() did not block on the card"
    carded = store.pending()
    assert [approval.tool for approval in carded] == ["kill_session"]
    assert answers == []

    assert store.withdraw_all(carded[0].turn_id or "") == 1

    assert returned.wait(WAIT_S), "the withdrawal never released the caller"
    worker.join(WAIT_S)
    assert not worker.is_alive()
    assert answers == [
        AuthzOutcome(
            allowed=False,
            approved_by=ApprovedBy.WITHDRAWN,
            approval_id=carded[0].id,
            reason=WITHDRAWN_TEXT,
        )
    ]
    assert recorder.bumps == [AnomalyKind.APPROVAL_WITHDRAWN]
    assert recorder.kinds() == [APPROVAL_CREATED_KIND, APPROVAL_DECIDED_KIND]
    # The summary the card carried is the tool's own description, redacted —
    # and it reached the stream rather than only the store.
    created = recorder.events[0]
    assert created.payload["summary"] == describe(a_tool(), {"session_id": "s1"})
    assert created.payload["deadline_at"] == carded[0].deadline_at


def test_a_click_is_the_only_thing_that_produces_user_and_the_declared_denial() -> None:
    """K23 and RD-T11-2 at the seam that produces them.

    `policy.decide()` cannot reach `ApprovedBy.USER` — T3 asserts that over its
    whole table, because a pure function of three enums cannot know whether a
    person acted. A click on a card is what knows, and this is where it lands.
    The denial's wording is `export.DENIED_TEXT`, compared **by identity**.
    """
    for clicked, expected in (
        (ApprovalOutcome.APPROVED, AuthzOutcome(True, ApprovedBy.USER, "", None)),
        (ApprovalOutcome.REJECTED, AuthzOutcome(False, None, "", DENIED_TEXT)),
    ):
        recorder = _Recorder()
        store = a_store()
        authorize = an_authorizer(store, recorder)
        answers: list[AuthzOutcome] = []
        entered, returned = threading.Event(), threading.Event()

        def call() -> None:
            entered.set()
            answers.append(authorize(a_tool(), {}, a_context()))
            returned.set()

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        assert entered.wait(WAIT_S)
        assert not returned.wait(NOT_YET_S), "authorize() did not block on the card"
        carded = store.pending()
        assert [approval.tool for approval in carded] == ["kill_session"]

        assert store.decide(carded[0].id, clicked) is True
        assert returned.wait(WAIT_S), "the click never released the caller"
        worker.join(WAIT_S)
        assert not worker.is_alive()

        assert answers == [
            AuthzOutcome(
                allowed=expected.allowed,
                approved_by=expected.approved_by,
                approval_id=carded[0].id,
                reason=expected.reason,
            )
        ]
        # A decision is not an anomaly: neither a click nor a decline is counted.
        assert recorder.bumps == []
        if expected.reason is not None:
            assert answers[0].reason is DENIED_TEXT


def test_two_callers_on_one_approval_are_both_released() -> None:
    """E-M4-14: two `tool_use` blocks can await the same card.

    Asserted because the implementation claims it — `_resolve` calls
    `notify_all`, and waking one waiter would leave the other blocked until its
    own deadline. A docstring is not a proof; this is `MUT-19`'s target.
    """
    store = a_store()
    approval = create_one(store)
    callers = [_Caller(store, approval.id, timeout_s=WAIT_S * 10) for _ in range(2)]
    for caller in callers:
        caller.start()
    assert [pending.id for pending in store.pending()] == [approval.id]
    for caller in callers:
        assert not caller.returned.wait(NOT_YET_S), "await_decision did not block"

    assert store.decide(approval.id, ApprovalOutcome.APPROVED) is True

    for caller in callers:
        assert caller.returned.wait(WAIT_S), "a waiter was left blocked"
        caller.join()
        assert caller.outcomes == [ApprovalOutcome.APPROVED]


def test_the_redaction_rule_has_one_definition_in_the_build() -> None:
    """§13's redaction pass is one rule, and now one **object** (RD-T4-3, closed).

    `approvals.py` could not import `audit.py`'s copy: `audit.py` imports
    `shepherd.logs.jsonl`, the gate lives behind `invoke()`, and `cli/` imports
    `registry` — so that import would have dragged `shepherd.logs` into `shepherd
    status`, the transitive hole `types.py`'s docstring exists to refuse, and the
    shipped boundary rule checks only **direct** importers so it would have
    passed while being defeated. The values moved to `types.py`, which is
    stdlib-only; both modules import them.

    **Identity, not comparison.** Two frozensets that are equal today can be
    edited apart tomorrow; `is` cannot. What keeps a *third* declaration from
    appearing is structural and lives in `tests/boundaries/
    test_one_definition_site.py::test_the_redaction_rule_has_one_definition_site`.
    """
    from shepherd.toolsurface import audit, types

    assert SECRET_KEY_MARKERS is audit.SECRET_KEY_MARKERS is types.SECRET_KEY_MARKERS
    assert REDACTED is audit.REDACTED is types.REDACTED
    # And every marker actually redacts, so a narrowed set is red here too.
    assert SECRET_KEY_MARKERS
    for marker in sorted(SECRET_KEY_MARKERS):
        summary = describe(a_tool(), {f"a_{marker}_arg": "SHOULD-NOT-APPEAR"})
        assert "SHOULD-NOT-APPEAR" not in summary, marker
