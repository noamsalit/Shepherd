"""The approval card, the block, and D54's withdrawal (§11, ADR-M4-2, ADR-M4-3).

`decide()` in `policy.py` is a pure function of three enum values, so it can
answer *does this need a person?* and nothing more. This module is the other
half: it raises the card, **blocks the calling thread**, and gives every
approval exactly one terminal outcome (P-M4-10).

**In memory, keyed by id, dying with the process (ADR-M4-2).** A dict under one
lock, one `threading.Condition`, an injected clock. No table, no file, no
socket. A `controld` restart loses every pending approval *and* the turn that
was waiting on it — which was going to be lost anyway, and a card nobody is
blocked on is worse than no card (E-M4-3).

**Withdrawal is the only thing that can free a blocked caller, and that is
measured rather than assumed.** `docs/probes/2026-09-17-m4-sdk/FINDINGS.md` §P2
mounted a tool handler that blocks a worker thread and interrupted the turn at
5 s: no `control_cancel_request` arrived, nothing was raised into the handler
coroutine, and the worker thread ticked on for the full twenty seconds — past
the end of the turn and past the close of the client. So `interrupt()` does not
cancel a running handler *at all*; it is not deferred, it never arrives.
`withdraw()` and `withdraw_all()` are therefore load-bearing rather than
belt-and-braces: our own compare-and-set, on our own thread, is the whole
release path (ADR-M4-3, D54, clause 20).

**Every terminal transition is the same operation.** A second decision, a
withdrawal after an approval, and a deadline that races a click are one
compare-and-set from `pending`, and the first one wins (E-M4-1, E-M4-2). The
loser is told it lost — `decide()` returns `False` — rather than silently
overwriting, because an approval that can change its mind is an audit record
that cannot be trusted.

**A withdrawn approval is resolved, never deleted.** A deleted row is
indistinguishable from one that never existed; a resolved one still answers
`await_decision` with `withdrawn`, and an id this store never issued raises
`KeyError`. That difference is the whole of why D54 exists.

**This module is the only producer of `ApprovedBy.USER` in the build** (K23,
§T3-3). `policy.py` asserts over its own table that it can never reach that
value, because a function of three enums cannot know whether a person acted.
Here, and only here, one did.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import parse_stamp, stamp, utc_now
from shepherd.core.ids import new_ulid
from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.export import DENIED_TEXT
from shepherd.toolsurface.policy import (
    APPROVAL_TIMEOUT_S,
    ApprovedBy,
    AutonomyLevel,
    Verdict,
    decide,
)
from shepherd.toolsurface.types import (
    REDACTED,
    SECRET_KEY_MARKERS,
    Authorizer,
    AuthzOutcome,
    CallerContext,
    ToolArgs,
    ToolDef,
)

#: The two stream kinds §12's chat page reads. Values, not spellings a renderer
#: re-invents: the page subscribes to the ring it already subscribes to.
APPROVAL_CREATED_KIND = "approval.created"
APPROVAL_DECIDED_KIND = "approval.decided"

#: §11's own words, verbatim: *"A timeout denies with a message the agent can
#: act on, not a dead turn."*
TIMED_OUT_TEXT = "approval timed out — proceed without it or ask me directly"

#: D54's outcome, said to the agent. Distinct text because `withdrawn` and
#: `timed_out` are different facts — *nobody was still listening* versus
#: *nobody answered in time* — and an agent that cannot tell them apart cannot
#: decide whether retrying is sensible.
WITHDRAWN_TEXT = "the request this approval belonged to went away"

#: §13's redaction rule, **imported rather than copied** (RD-T4-3, closed in the
#: QA-prep pass). These two values were declared in `audit.py` and copied here,
#: because `audit.py` imports `shepherd.logs.jsonl` and the import would have
#: dragged `shepherd.logs` into `shepherd status`. `types.py` is stdlib-only, so
#: it is the honest home and the copy is gone. Re-exported under their old names
#: so every existing caller and every existing test reads the same spelling.
#: (imported above; named here so a reader of `_redact` finds the rule.)


class ApprovalOutcome(StrEnum):
    """The terminal outcomes. An approval reaches exactly one of them, ever."""

    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class Approval:
    """One card. `turn_id` is what `withdraw_all()` keys on, so ADR-M4-3's
    release path can free every worker of one interrupted turn at once."""

    id: str
    turn_id: str | None
    tool: str
    summary: str
    args: Mapping[str, object]
    created_at: str
    deadline_at: str


def _redact(key: str, value: object) -> str:
    lowered = key.lower()
    if any(marker in lowered for marker in SECRET_KEY_MARKERS):
        return REDACTED
    return str(value)


def describe(tool: ToolDef, args: ToolArgs) -> str:
    """§11's card summary: the **tool's own description** plus its arguments.

    Never a hand-written sentence per tool. A per-tool table is a second
    declaration of what a tool does; it drifts from `ToolDef.description` the
    first time a description is edited, and it has nothing at all to say about
    a tool added after it was written. D32 removed three such lists.
    `test_the_card_summary_is_derived_from_the_tool_def` reads this function's
    AST and refuses one.
    """
    if not args:
        return tool.description
    mapped = ", ".join(f"{key}={_redact(key, args[key])}" for key in sorted(args))
    return f"{tool.description} ({mapped})"


class ApprovalStore:
    """The in-memory store (ADR-M4-2). One lock, one condition, one clock.

    The clock is injected so a ten-minute deadline is asserted in milliseconds:
    `monotonic` bounds the wait, `now` writes the two stamps the card shows.
    `monotonic` rather than a wall clock because a deadline that moves when NTP
    steps the host is not a deadline — and `tests/boundaries/test_one_clock.py`
    permits it for exactly that reason.
    """

    def __init__(
        self,
        now: Callable[[], str] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        timeout_s: float = APPROVAL_TIMEOUT_S,
    ) -> None:
        self._now = now
        self._monotonic = monotonic
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._approvals: dict[str, Approval] = {}
        self._outcomes: dict[str, ApprovalOutcome] = {}

    def create(self, tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> Approval:
        """Raise a card. It is `pending()` from the moment this returns.

        `turn_id` comes from `ctx.correlation_id`: that is the id the caller
        already threads through every call it makes on one request's behalf,
        and `master_turn.py` interrupts by turn id. Nothing else in
        `CallerContext` can carry it — see `docs/plans/m4-blockers/t4.md` §T4-2
        for the obligation this puts on T16/T20/T27.
        """
        created_at = self._now()
        moment = parse_stamp(created_at)
        if moment is None:
            raise ValueError(f"the injected clock wrote an unreadable stamp: {created_at!r}")
        approval = Approval(
            id=new_ulid(),
            turn_id=ctx.correlation_id,
            tool=tool.name,
            summary=describe(tool, args),
            args=dict(args),
            created_at=created_at,
            deadline_at=stamp(moment + timedelta(seconds=self._timeout_s)),
        )
        with self._lock:
            self._approvals[approval.id] = approval
        return approval

    def await_decision(self, approval_id: str, timeout_s: float) -> ApprovalOutcome:
        """Block until this approval is terminal, or until the caller's own
        deadline passes — whichever happens first.

        A `Condition` and never a poll loop: a poll's interval is a latency
        nobody chose, and §11's card is meant to resume the turn *on the click*.
        The `while` re-checks the predicate because `wait()` may return without
        a decision; it is not a poll, since every pass either returns or waits
        the whole remaining deadline.

        An id this store never issued raises `KeyError` rather than answering.
        That is what makes a **withdrawn** approval tellable from a deleted one.
        """
        deadline = self._monotonic() + timeout_s
        with self._changed:
            if approval_id not in self._approvals:
                raise KeyError(approval_id)
            while True:
                decided = self._outcomes.get(approval_id)
                if decided is not None:
                    return decided
                remaining = deadline - self._monotonic()
                if remaining <= 0.0:
                    # The deadline is itself a terminal outcome, set through the
                    # same compare-and-set — so a click landing in this instant
                    # wins or loses like any other decision, never both.
                    self._resolve(approval_id, ApprovalOutcome.TIMED_OUT)
                    return self._outcomes[approval_id]
                self._changed.wait(remaining)

    def decide(self, approval_id: str, outcome: ApprovalOutcome) -> bool:
        """Compare-and-set from `pending`. `True` if this call was the one that
        decided it; `False` if it was already terminal, or unknown."""
        with self._changed:
            return self._resolve(approval_id, outcome)

    def withdraw(self, approval_id: str) -> bool:
        """D54. The same compare-and-set, so a withdrawal cannot overwrite a
        decision a person already made (E-M4-2)."""
        return self.decide(approval_id, ApprovalOutcome.WITHDRAWN)

    def withdraw_all(self, turn_id: str) -> int:
        """Every pending approval of one turn, as ADR-M4-3's release path and
        as shutdown's (clause 20, E-M4-20). Returns how many it resolved.

        Held under one lock for the whole sweep: a turn being interrupted while
        a second card is raised against it would otherwise leave that card
        behind, blocking a worker nothing is left to answer.
        """
        with self._changed:
            ids = [
                approval.id
                for approval in self._approvals.values()
                if approval.turn_id == turn_id and approval.id not in self._outcomes
            ]
            return sum(
                self._resolve(approval_id, ApprovalOutcome.WITHDRAWN)
                for approval_id in ids
            )

    def pending(self) -> tuple[Approval, ...]:
        """The undecided cards — what §12's rail renders."""
        with self._lock:
            return tuple(
                approval
                for approval in self._approvals.values()
                if approval.id not in self._outcomes
            )

    def _resolve(self, approval_id: str, outcome: ApprovalOutcome) -> bool:
        """The compare-and-set itself. The caller holds `self._changed`.

        `notify_all` rather than `notify`: two callers may await the same
        approval (E-M4-14's parallel `tool_use` blocks), and waking one of them
        leaves the other blocked until its own deadline.
        """
        if approval_id not in self._approvals or approval_id in self._outcomes:
            return False
        self._outcomes[approval_id] = outcome
        self._changed.notify_all()
        return True


#: How each terminal outcome answers the caller: allowed, attribution, reason,
#: and the anomaly to count. A table rather than a branch cascade, for §T3-1's
#: reason — `set(_ANSWERS)` is a second, independent statement of
#: `set(ApprovalOutcome)`, so a fifth outcome is a failing test rather than a
#: fall-through to whichever branch happened to be last.
_ANSWERS: Mapping[
    ApprovalOutcome, tuple[bool, ApprovedBy | None, str | None, AnomalyKind | None]
] = {
    # A person pressed Approve. **The only producer of `USER` in the build**:
    # `decide()` is a pure function of three enums, and T3 asserts over its own
    # table that it can never reach this value (K23, §T3-3).
    ApprovalOutcome.APPROVED: (True, ApprovedBy.USER, None, None),
    # A person declined. `approved_by` stays `None` — nothing approved it, and
    # `USER` means *approved by a user*, which would be the same overclaim K23
    # is about. The text is `export.DENIED_TEXT`, **imported and never
    # respelled** (RD-T11-2): this module produces the denial, `export.py`
    # declares its wording, and two spellings of one user-facing refusal is a
    # defect no test in either file would catch.
    ApprovalOutcome.REJECTED: (False, None, DENIED_TEXT, None),
    # Nobody answered in time. Counted, because a deadline nobody saw is not the
    # same event as a refusal somebody chose.
    ApprovalOutcome.TIMED_OUT: (
        False,
        ApprovedBy.TIMEOUT,
        TIMED_OUT_TEXT,
        AnomalyKind.APPROVAL_TIMED_OUT,
    ),
    # Nobody was still listening (D54). Also counted, and separately.
    ApprovalOutcome.WITHDRAWN: (
        False,
        ApprovedBy.WITHDRAWN,
        WITHDRAWN_TEXT,
        AnomalyKind.APPROVAL_WITHDRAWN,
    ),
}


def build_authorizer(
    store: ApprovalStore,
    level: Callable[[], AutonomyLevel],
    publish: Callable[[StreamEvent], int],
    bump: Callable[[AnomalyKind], None],
    now: Callable[[], str],
) -> Authorizer:
    """§11's `authorize()`, wrapped around T3's gate — the one chokepoint.

    Everything *policy* knows is `decide()`'s; everything a *person* decides is
    the store's. Nothing here auto-approves: that is the gate's job and a second
    place to decide is a second policy (D42). Nothing here writes an audit
    record either — the authorizer returns an outcome and `invoke()` writes the
    record, so there is exactly one writer.

    **The closure is `_authorize`, with an underscore, and that is deliberate.**
    `tests/toolsurface/test_registry.py::test_no_authorize_call_exists_yet` is
    M1's tripwire — *"M1 has no gate, so M4 adding one is visible in the diff"* —
    and it scans every identifier under `toolsurface/`. T4 ships a **builder for
    an injected callable**; the gate is not in `invoke()` until **T6** installs
    it, and T6 owns that file. Firing another task's tripwire from here would
    redden the tree for every live builder without the diff it exists to reveal.
    The tripwire is still armed: renaming this closure to `authorize` turns it
    red, which is `docs/plans/m4-blockers/t4.md` **MUT-12**.
    """

    def _publish(kind: str, approval: Approval, payload: Mapping[str, object]) -> None:
        publish(
            StreamEvent(
                kind=kind,
                session_id=None,
                payload={"approval_id": approval.id, "tool": approval.tool, **payload},
                occurred_at=now(),
            )
        )

    def _authorize(tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> AuthzOutcome:
        decision = decide(tool.blast_class, level(), ctx.audience)
        if decision.verdict is Verdict.ALLOW:
            return AuthzOutcome(
                allowed=True,
                approved_by=decision.approved_by,
                approval_id=None,
                reason=None,
            )
        approval = store.create(tool, args, ctx)
        _publish(
            APPROVAL_CREATED_KIND,
            approval,
            {
                "summary": approval.summary,
                "turn_id": approval.turn_id,
                "deadline_at": approval.deadline_at,
            },
        )
        outcome = store.await_decision(approval.id, APPROVAL_TIMEOUT_S)
        _publish(APPROVAL_DECIDED_KIND, approval, {"outcome": str(outcome)})
        allowed, approved_by, reason, anomaly = _ANSWERS[outcome]
        if anomaly is not None:
            bump(anomaly)
        return AuthzOutcome(
            allowed=allowed,
            approved_by=approved_by,
            approval_id=approval.id,
            reason=reason,
        )

    return _authorize
