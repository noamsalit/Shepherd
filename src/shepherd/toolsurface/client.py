"""The one Shepherd module `master/` may import (D19, D35, §5.0).

D19 says the master reaches the rest of the system *"only through the tool-surface
client"*, singular, and gives its own reason: *"if it grows a private read path,
the 'one direction, one store' invariant is gone."* **So every public name below
is a capability granted to `master/`**, and the list is short on purpose. An
allow-list with one entry is a rule a reviewer holds in their head; an allow-list
with four is a rule that grows to five. `tests/toolsurface/test_client.py`
asserts the name set and the import set as **equalities**, so a member added
without a line in that test is a failing build rather than a review comment.

**Why this module exists at all, by the deletion test.** Inline it at its call
sites and the complexity does not vanish — it reappears in `master/` as a
`CallerContext` the master constructs for itself. A caller that can choose its
own audience has no audience, and the audience filter is the only thing standing
between an orchestrator agent and the `HUMAN`-only surface. `MASTER_AUDIENCE` is
pinned here, once, and `call()` is the only way past it.

**What is deliberately absent, and why.** No `Store`, no `registered_tools`, no
`ToolDef`, no `publish`. A master holding the registry could read around
`invoke()` — which is the gate, the audit point and the validator all at once
(D32, D38, D53). A master holding `ToolDef` could read a tool's `blast_class`
and reason about its own permissions, which is the same defect `ExportedTool`
carries three fields to avoid. And there is no per-tool convenience: the master
calls tools **by name through one function**, which is what makes the audience
filter total rather than a property of however many wrappers happen to exist.

**The wiring, and why four of the seven members need it (§T16-1).** `call()` and
`master_tools()` sit straight on `export.py` — same layer, downward import, done.
The other four cannot be written that way and stay inside D19:

* `autonomy_level()` is a read of `app_state`, and importing `Store` here is the
  exact name the client's own check forbids;
* `wake_text()` is `orchestration.wake`'s, and `orchestration/` is **L3** — L4
  importing it would be an upward import (§5.0);
* the two withdrawals are `approvals.py`'s, which does not exist in this tree
  yet, and whose outcome type the plan's `Consumes` block names but neither
  signature uses.

So they arrive as four opaque callables that the composition root installs
through `bind_master_client()` — the same shape `orchestration/master_turn.py`
already uses for `publish` and `withdraw_turn_approvals`, and the same shape
`registry.register()` / `stream.reset_stream()` use for the other two L4
module-globals. **The wiring is the root's side of the seam, not the master's:**
`master/` calls the four verbs and never sees `bind_master_client`, so D19's
budget is still the seven members the plan lists.

No lock. Unlike `registry._TOOLS` this is a single reference assigned once at
startup, before anything binds (ADR-7's one-writer rule), and rebinding a module
global is atomic — a lock here would guard a race that composition order already
excludes.

**Unbound is a typed refusal, never an `AttributeError` and never a silent
default.** A client that answered `autonomy_level() == 2` because nobody wired it
would auto-approve nothing and ask for everything on a level-3 build — a
misconfiguration rendered as a policy. `MasterClientUnbound` says which it is.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from shepherd.core.master import ExportedTool
from shepherd.toolsurface.export import call_exported, exported_tools
from shepherd.toolsurface.types import Audience, CallerContext

#: The audience the master calls with, pinned here and nowhere else. It is a
#: module constant rather than a parameter because a caller that can choose its
#: own audience has no audience.
MASTER_AUDIENCE: Audience = Audience.MASTER


class MasterClientUnbound(RuntimeError):
    """A member was called before the composition root wired it.

    Typed, because a bare `RuntimeError` at a seam is an untyped refusal and a
    caller asserting on its message is asserting on a spelling (RD-T17-2).
    """


@dataclass(frozen=True)
class _Wiring:
    """The four callables the root installs. Private: `master/` never holds it."""

    withdraw_approval: Callable[[str], bool]
    withdraw_turn_approvals: Callable[[str], int]
    autonomy_level: Callable[[], int]


_WIRING: _Wiring | None = None


def bind_master_client(
    *,
    withdraw_approval: Callable[[str], bool],
    withdraw_turn_approvals: Callable[[str], int],
    autonomy_level: Callable[[], int],
) -> None:
    """Install the four things this layer cannot reach on its own.

    Keyword-only: three callables of which two take a string and return different
    things, and a positional swap between them would be a withdrawal that
    reports a count as a boolean — always true, including for an approval that
    was never there.
    """
    global _WIRING
    _WIRING = _Wiring(
        withdraw_approval=withdraw_approval,
        withdraw_turn_approvals=withdraw_turn_approvals,
        autonomy_level=autonomy_level,
    )


def reset_master_client() -> None:
    """Back to unbound. The composition root's startup, and every test's."""
    global _WIRING
    _WIRING = None


def _wiring() -> _Wiring:
    if _WIRING is None:
        raise MasterClientUnbound(
            "the tool-surface client is not wired; the composition root calls"
            " bind_master_client() before the master runs a turn"
        )
    return _WIRING


def master_tools() -> tuple[ExportedTool, ...]:
    """What the master may call, as the three fields a model needs.

    The audience is this module's, not the caller's — that is the whole member.
    """
    return exported_tools(MASTER_AUDIENCE)


def call(
    name: str, args: Mapping[str, object], caller_id: str, correlation_id: str
) -> Mapping[str, object]:
    """Run one tool as the master and hand back the `content[]` + `is_error` shape.

    Everything that decides whether this call happens — the audience check, the
    schema validation, the gate and the audit record — is `invoke()`'s, reached
    through `export.call_exported`. There is no second path, which is what makes
    "a capability absent from the registry has no surface that can reach it"
    true of the master as well (D32).

    `actor_kind` is left to default: `Audience.MASTER` already derives it, and a
    second spelling of one fact is a fact two components can disagree about.
    """
    return call_exported(
        name,
        args,
        CallerContext(
            audience=MASTER_AUDIENCE, caller_id=caller_id, correlation_id=correlation_id
        ),
    )


def withdraw_approval(approval_id: str) -> bool:
    """Cancel one pending approval (D54). `False` if it was not pending."""
    return _wiring().withdraw_approval(approval_id)


def withdraw_turn_approvals(turn_id: str) -> int:
    """Cancel every approval raised by one turn, and say how many (ADR-M4-3).

    The release path `interrupt_master()` runs **before** `interrupt()`: probe P2
    measured that no cancellation of any kind reaches a running in-process
    handler, so our own store is the only thing that can free a worker blocked
    on a card before its 600 s deadline.
    """
    return _wiring().withdraw_turn_approvals(turn_id)


def autonomy_level() -> int:
    """D8's toggle, as the number `master/prompt.py` interpolates."""
    return _wiring().autonomy_level()


# `wake_text()` was retired here by the router (RD-T16-7a), and the reason is a
# correctness one rather than tidiness. It drained the wake set — and so does
# `orchestration/master_turn.py`'s `TurnDriver`, which opens every turn with the
# summary. **Two drains is D31's lost stop**: a stop landing between them is
# stamped as already seen and never wakes anybody. That is the same defect
# RD-T27-3 corrected in Flow A step 8, found independently from a second
# direction within the hour — which says the drain is easy to call twice, so the
# design makes it impossible rather than merely avoided.
#
# The turn driver is the single drain site. If the master ever needs to ask what
# is waiting *mid-turn*, that is a **`peek`-based** tool in `tools_master.py` and
# it must not stamp — `orchestration/wake.py::peek` exists for exactly this and
# T9 built it as the non-stamping twin.
