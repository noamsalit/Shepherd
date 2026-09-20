"""T23 — M4's own capabilities, declared where every other capability is (D32).

Ten `ToolDef`s over verbs that live below: the approval rail, D8's toggle, §12's
chat post, D54's interrupt, §12's *"while you were away"*, D25's audit view, and
§11's two session escalations. **No handler logic lives here** — `tools_*.py`
modules in this build are declarations, and `tools_m1.py` / `tools_m3.py` are the
shape. What is written out below is the *projection* each tool returns, because a
consumer-facing whitelist is §13's and belongs at the response sink.

**Three declarations are load-bearing enough to say out loud.**

* **`GATE_TOOLS` is `HUMAN`-only, and P-M4-15 asserts it structurally** — the set
  of tools that can change the gate and the set reachable by an agent are
  disjoint, both enumerated from the registry at test time. The check carries the
  subset assertion **above** the disjointness, because an empty intersection is
  exactly what a gate tool renamed out of the registry produces (clause 15).
* **`get_audit_log` carries `audiences={HUMAN}`** (RD11). §11 lists the tool and
  states no audience; `HUMAN` is this build's choice and it is recorded as a
  decision rather than slipped in, because an agent reading the audit log reads
  every other agent's actions — including approvals it was denied.
* **`master_send` is `local_write`, not `local_destructive`.** Posting a message
  to your own orchestrator is not destructive. What the master then *does* is
  gated call by call, which is the whole design.

**`wake_summary` peeks and never drains** (RD-T16-7a). `orchestration/wake.py`
ships `drain` and `peek` as twins and only `drain` moves the stamp;
`master_turn.py`'s `TurnDriver` is the **single** drain site, opening each turn
with the summary. A second drain is D31's lost stop: a stop landing between the
two is stamped as already seen and never wakes anybody. That defect arrived twice
in one hour from two directions (RD-T27-3, RD-T16-7a), which says the drain is
easy to call twice — so this tool calls `peek`, and
`test_wake_summary_does_not_stamp` asserts `master_last_turn_at` is untouched
across two calls rather than trusting the spelling.

**`report_blocked` and `request_help` refuse, and that is G-M4-15 said honestly.**
`registry.py`'s `_run` is `data = tool.handler(args)`: `invoke()` checks the
caller's audience and then **discards the caller**. A session-audience handler
therefore cannot know *which* session called it, and the repair the Track C cut
names — `ctx` bound into the call, plus an enumerated per-tool scope property —
is not M4's. The alternative, a `session_id` argument, is precisely the unscoped
cross-project write API that cut refused. So the handlers raise
`ToolArgumentRefused`, whose message names the missing fact; the tools are
registered because the registry is the declaration and a capability absent from
it has no surface at all.

**Two names in the plan's `Produces` block are not here**, and both omissions are
recorded in `docs/plans/m4-blockers/t23.md` §T23-2 rather than satisfied quietly:
`MASTER_SESSION_KEY` is already declared by `orchestration/master_turn.py` (a
second spelling is the defect RD-T4-3 and §T6-4 each record one instance of), and
`MASTER_RUNTIME_KEY` has no consumer anywhere in the tree — the "no caller"
register's exact failure mode, created deliberately.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from shepherd.orchestration.master_turn import TurnRefused, TurnStarted
from shepherd.orchestration.wake import WakeSummary, peek, render_wake_text
from shepherd.store.db import Store
from shepherd.toolsurface.approvals import Approval, ApprovalOutcome, ApprovalStore
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
    arg_str,
)

__all__ = [
    "AUTONOMY_LEVEL_KEY",
    "DEFAULT_AUTONOMY_LEVEL",
    "GATE_TOOLS",
    "UNREACHABLE_SESSION_TOOLS",
    "autonomy_level",
    "decide_approval",
    "get_audit_log",
    "interrupt_master",
    "list_approvals",
    "master_send",
    "project_approval",
    "register_master_tools",
    "set_autonomy_level",
    "wake_summary",
]

Clock = Callable[[], str]
SendTurn = Callable[[str], TurnStarted | TurnRefused]
InterruptMaster = Callable[[], bool]

#: The tools that can change what the gate decides — P-M4-15's left-hand set.
#: `set_autonomy_level` rewrites D8's toggle, which is one of `decide()`'s three
#: inputs; `decide_approval` releases a call the gate blocked. Both are
#: `HUMAN`-only **by construction**, and clause 15 asserts the disjointness with a
#: subset assertion above it so a rename cannot make the check vacuous.
GATE_TOOLS: frozenset[str] = frozenset({"set_autonomy_level", "decide_approval"})

#: G-M4-15: registered, and reachable by nothing after the Track C cut. Named
#: here and asserted as a **set equality** in the test, so a third `SESSION`
#: tool appearing unnoticed is a failing build rather than a surprise.
UNREACHABLE_SESSION_TOOLS: frozenset[str] = frozenset({"report_blocked", "request_help"})

#: §7's `app_state` key holding D8's toggle. `store/` has no constant for it — it
#: is a key in a key/value table, and the component that owns the meaning owns
#: the spelling (`wake.MASTER_LAST_TURN_KEY`'s reason, one layer over).
AUTONOMY_LEVEL_KEY = "autonomy_level"

#: What an unwritten — or unreadable — toggle means. Level 2 **asks** for every
#: destructive call and level 3 auto-approves, so the default is the level that
#: asks: a misconfiguration must not read as a licence. `app_state` hands back
#: whatever JSON the key holds, which is why a value that is not a member of
#: `AutonomyLevel` is treated as *no level* rather than coerced into one.
DEFAULT_AUTONOMY_LEVEL: AutonomyLevel = AutonomyLevel.LEVEL_2

#: §11's card decisions, as the two words the UI sends. A mapping rather than a
#: branch pair, so `set(_CHOICES.values())` is a second statement of which
#: outcomes a *person* can reach — `TIMED_OUT` and `WITHDRAWN` are nobody's click.
_CHOICES: Mapping[str, ApprovalOutcome] = {
    "approve": ApprovalOutcome.APPROVED,
    "reject": ApprovalOutcome.REJECTED,
}

#: §11's default tail length for D25's audit view.
DEFAULT_AUDIT_LIMIT = 50

_HUMAN_ONLY = frozenset({Audience.HUMAN})
_HUMAN_AND_MASTER = frozenset({Audience.MASTER, Audience.HUMAN})
_SESSION_ONLY = frozenset({Audience.SESSION})

_NO_ARGS: Mapping[str, object] = {"type": "object", "properties": {}}

#: Why the two `SESSION` tools cannot act. Written once, because it is the same
#: missing fact for both and two spellings of one refusal is a defect nobody
#: notices until they drift (RD-T11-2).
NO_CALLER_TEXT = (
    "this tool cannot act: invoke() discards the caller after the audience check,"
    " so the handler cannot know which session is reporting (G-M4-15, G-M4-18)"
)


# ----- the projections --------------------------------------------------------


def project_approval(approval: Approval) -> dict[str, object]:
    """§12's rail row.

    **The raw `args` are deliberately absent.** `summary` is `describe()`'s,
    which redacts secret-shaped keys (§13); the argument mapping is not redacted
    and putting it on a page would render an unredacted token beside a button.
    The card shows what the call *is*, which is what a person decides on.
    """
    return {
        "approval_id": approval.id,
        "turn_id": approval.turn_id,
        "tool": approval.tool,
        "summary": approval.summary,
        "created_at": approval.created_at,
        "deadline_at": approval.deadline_at,
    }


def project_turn(answer: TurnStarted | TurnRefused) -> dict[str, object]:
    """One shape for both answers, the way `project_rename` carries a refusal.

    A refused turn is a **result**, not a `Failure`: the call reached the driver
    and the answer is *no* (RD7/E-M4-4). Rendering it as an error would tell a
    page that posting failed when the reason is that a turn is already running.
    """
    if isinstance(answer, TurnStarted):
        return {
            "started": True,
            "turn_id": answer.turn_id,
            "started_at": answer.started_at,
            "reason": None,
        }
    return {"started": False, "turn_id": None, "started_at": None, "reason": answer.reason}


# ----- the verbs --------------------------------------------------------------


def get_audit_log(root: Path, limit: int) -> dict[str, object]:
    """D25's single UI exception: a literal tail, newest first.

    `read_audit_records` is the **only** reader of the directory (its own
    docstring); this is the projection over what it returns.
    """
    return {"records": list(read_audit_records(root, limit)), "limit": limit}


def list_approvals(approvals: ApprovalStore) -> dict[str, object]:
    """The undecided cards — §12's rail, in the store's own order."""
    return {"approvals": [project_approval(card) for card in approvals.pending()]}


def decide_approval(
    approvals: ApprovalStore, approval_id: str, choice: str
) -> dict[str, object]:
    """A person's click, as the compare-and-set `ApprovalStore` already owns.

    `decided` is `False` when this call was not the one that decided it — a
    second click, a click that raced the 600 s deadline, or an id this store
    never issued. The loser is **told it lost** rather than silently overwriting
    (E-M4-1, E-M4-2), so `outcome` is `None` in that case: nothing this call did
    produced one.
    """
    outcome = _CHOICES.get(choice)
    if outcome is None:
        raise ToolArgumentRefused(
            f"choice {choice!r} is not one of {sorted(_CHOICES)}"
        )
    decided = approvals.decide(approval_id, outcome)
    return {
        "approval_id": approval_id,
        "decided": decided,
        "outcome": str(outcome.value) if decided else None,
    }


def autonomy_level(store: Store) -> AutonomyLevel:
    """D8's toggle as a **member**, or the default.

    `app_state` hands back whatever JSON the key holds, so the value is narrowed
    here rather than trusted — the same narrowing `wake._since` applies to the
    stamp, and for the same reason: a stored value that this build has no member
    for is *no level*, and the level that asks is the safe reading of it.
    """
    stored = store.get_app_state(AUTONOMY_LEVEL_KEY)
    if isinstance(stored, int) and not isinstance(stored, bool):
        for level in AutonomyLevel:
            if int(level) == stored:
                return level
    return DEFAULT_AUTONOMY_LEVEL


def set_autonomy_level(store: Store, level: int) -> dict[str, object]:
    """The gate-changing write. `MASTER` is absent from this tool's audiences.

    The accepted values are `AutonomyLevel` **enumerated here**, never a range: a
    third level is a Decision and adding one to the enum should widen this tool
    by construction rather than by somebody remembering to edit a bound.
    """
    members = {int(member): member for member in AutonomyLevel}
    if level not in members:
        raise ToolArgumentRefused(
            f"autonomy level {level!r} is not one of {sorted(members)}"
        )
    previous = autonomy_level(store)
    store.set_app_state(AUTONOMY_LEVEL_KEY, int(members[level]))
    return {"level": int(members[level]), "previous": int(previous)}


def master_send(send_turn: SendTurn, text: str) -> dict[str, object]:
    """§12's chat post. One turn at a time is the driver's rule, not this one's."""
    return project_turn(send_turn(text))


def interrupt_master(interrupt: InterruptMaster) -> dict[str, object]:
    """D54's trigger. `False` when nothing was live — not an error."""
    return {"interrupted": interrupt()}


def wake_summary(store: Store, now: Clock) -> dict[str, object]:
    """§12's *"while you were away"*, **without consuming it** (RD-T16-7a).

    `peek` is `drain`'s non-stamping twin, and the stamp is what makes a drain
    idempotent — so calling this mid-turn hands the master the same rows the
    turn driver already opened with, and moves nothing.

    `render_wake_text` is the summary's **one** renderer, so the text is built by
    passing the peeked rows through `WakeSummary`. `drained_at` carries this
    call's instant and nothing reads it back: the alternative is a second
    renderer in this module, and two spellings of §12's summary is a drift no
    test in either file would see.
    """
    items = peek(store)
    return {
        "items": [
            {
                "session_id": item.session_id,
                "title": item.title,
                "bucket": str(item.bucket.value),
                "why": item.why,
                "first_action": (
                    None if item.first_action is None else item.first_action.text
                ),
            }
            for item in items
        ],
        "text": render_wake_text(WakeSummary(items=items, drained_at=now())),
    }


def _no_caller(_args: ToolArgs, _ctx: CallerContext) -> object:
    """G-M4-15's two tools, refusing the only way they honestly can.

    A typed refusal rather than a silent success or an invented write: a tool
    that reported *blocked* against a session it guessed would be worse than one
    that says it cannot tell who is calling.
    """
    raise ToolArgumentRefused(NO_CALLER_TEXT)


# ----- registration -----------------------------------------------------------


def register_master_tools(
    *,
    store: Store,
    approvals: ApprovalStore,
    audit_root: Path,
    send_turn: SendTurn,
    interrupt_master: InterruptMaster,
    now: Clock,
) -> None:
    """The ten `ToolDef`s, registered by the composition root (T25).

    Keyword-only, like every other registrar in this package: `send_turn` and
    `interrupt_master` are two callables of different shapes and a positional
    swap between the store and the approval store is a type error nobody sees
    until a card is raised.
    """
    _register_audit_and_approvals(approvals, audit_root)
    _register_autonomy(store)
    _register_turn(send_turn, interrupt_master)
    _register_wake(store, now)
    _register_session_escalations()


def _register_audit_and_approvals(approvals: ApprovalStore, audit_root: Path) -> None:
    register(
        ToolDef(
            name="get_audit_log",
            description="The most recent decided calls, newest first (D25).",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: get_audit_log(
                audit_root, _arg_int(args, "limit", DEFAULT_AUDIT_LIMIT)
            ),
            # RD11: `HUMAN` only. An agent reading the audit log reads every
            # other agent's actions, including approvals it was denied.
            audiences=_HUMAN_ONLY,
        )
    )
    register(
        ToolDef(
            name="list_approvals",
            description="The approval cards still waiting for a decision.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_approvals(approvals),
            audiences=_HUMAN_ONLY,
        )
    )
    register(
        ToolDef(
            name="decide_approval",
            description="Approve or reject one pending approval.",
            input_schema={
                "type": "object",
                "properties": {
                    "approval_id": {"type": "string"},
                    "choice": {"type": "string"},
                },
                "required": ["approval_id", "choice"],
            },
            # It releases a blocked destructive call, so it is destructive.
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: decide_approval(
                approvals, arg_str(args, "approval_id"), arg_str(args, "choice")
            ),
            audiences=_HUMAN_ONLY,
        )
    )


def _register_autonomy(store: Store) -> None:
    register(
        ToolDef(
            name="get_autonomy_level",
            description="D8's autonomy toggle, as the number the prompt interpolates.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: {"level": int(autonomy_level(store))},
            # The master may **read** the level: `master/prompt.py` interpolates
            # it into the system prompt, so the fact is already in its context.
            audiences=_HUMAN_AND_MASTER,
        )
    )
    register(
        ToolDef(
            name="set_autonomy_level",
            description="Change D8's autonomy toggle.",
            input_schema={
                "type": "object",
                "properties": {"level": {"type": "integer"}},
                "required": ["level"],
            },
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: set_autonomy_level(store, _arg_int(args, "level", 0)),
            # **The gate-changing tool.** `MASTER` is absent, and P-M4-15 asserts
            # the absence structurally rather than trusting this line.
            audiences=_HUMAN_ONLY,
        )
    )


def _register_turn(send_turn: SendTurn, interrupt: InterruptMaster) -> None:
    register(
        ToolDef(
            name="master_send",
            description="Post a message to the orchestrator and open a turn.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            # `local_write`, deliberately: posting a message to your own
            # orchestrator is not destructive. What the master then does is
            # gated call by call, which is the whole design.
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: master_send(send_turn, arg_str(args, "text")),
            audiences=_HUMAN_ONLY,
        )
    )
    register(
        ToolDef(
            name="interrupt_master",
            description="End the turn in flight and release anything it blocked (D54).",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: interrupt_master(interrupt),
            audiences=_HUMAN_ONLY,
        )
    )


def _register_wake(store: Store, now: Clock) -> None:
    register(
        ToolDef(
            name="wake_summary",
            description="What stopped while you were away, without consuming it.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            # `peek`, never `drain` (RD-T16-7a). Two drains is D31's lost stop.
            handler=lambda args, ctx: wake_summary(store, now),
            audiences=_HUMAN_AND_MASTER,
        )
    )


def _register_session_escalations() -> None:
    """§11's two escalations — **reachable by nothing at M4** (G-M4-15)."""
    register(
        ToolDef(
            name="report_blocked",
            description="Declare that this session is blocked on something external (D18).",
            input_schema={
                "type": "object",
                "properties": {
                    "waiting_on": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["waiting_on", "detail"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=_no_caller,
            audiences=_SESSION_ONLY,
        )
    )
    register(
        ToolDef(
            name="request_help",
            description="Escalate a question only a human can answer (§11).",
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array"},
                },
                "required": ["question"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=_no_caller,
            audiences=_SESSION_ONLY,
        )
    )


def _arg_int(args: ToolArgs, key: str, default: int) -> int:
    """A required-shape integer argument. `invoke()` has already proved the type
    when the key is present; the default is this module's."""
    value = args.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolArgumentRefused(f"argument {key!r} is not an integer")
    return value
