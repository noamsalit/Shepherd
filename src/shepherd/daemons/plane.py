"""T25 — the process plane: the two things only the composition root can build.

**ADR-M4-6.** `controld.py` is at 140 of the 140 lines ADR-1's cap leaves it
(150, less M2's reserved 10), and a composition root sitting *on* its cap cannot
take its next wiring change additively. So M4's two remaining constructions live
here, in `daemons/` where the lines are, and the root's two edits are to lines it
already has: one import and one call.

**Why they are not in `toolsurface/compose.py`, where the rest of the wiring
is.** Both are things L4 may not say:

* **The master runtime is `shepherd.master`, which is L5.** `compose.py` is L4
  and §5.0 forbids the upward import; `test_compose_does_not_import_the_master_
  package` is that rule, asserted rather than remembered. The runtime therefore
  arrives at the composition as a **factory**, the way `ingest` already arrives
  as a `SocketPlan` rather than as a socket name L4 would have to know.
* **The audit sink is built over a `RotatingJsonlLog`, and DP3 (P-M4-6) pins
  `toolsurface/audit.py` as the single L4 importer of `shepherd.logs`.** The
  plan's prose has `compose.py` constructing the log from the root it already
  resolves; that construction is a **second** L4 logs importer and a failing
  build in `tests/boundaries/test_l4_import_rules.py`. Widening the rule to fit
  was the option the rule's own docstring refuses by name (K11), so the
  construction moved instead — `log_root(host)` is still the one resolver, read
  from here, so there is no second spelling of where the log lives.

**The turn id is an argument, and that is RD-T4-2's closing line.** T4 shipped
`withdraw_all(turn_id)` and nothing produced its key; T20 held the supplier and
T21 held its holder, and neither could name the live turn. `TurnDriver` now
hands `build_master` the id of the turn it is opening, this closes over it, and
the runtime keys every approval it raises on it. P2 measured that no
cancellation reaches a running in-process tool handler, so the withdrawal is the
**only** thing that can free a worker blocked on a card — and a key that merely
looks plausible would leave every one of them riding its full 600 s with every
test in the tree still green.
"""

from __future__ import annotations

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import MasterRuntime
from shepherd.daemons.shutdown import ShutdownOutcome, shut_down
from shepherd.host.base import HostPlatform
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import date_of
from shepherd.master.prompt import orchestrator_prompt
from shepherd.master.sdk_master import AgentSDKMaster
from shepherd.orchestration.master_turn import MASTER_SESSION_KEY
from shepherd.store.db import Store
from shepherd.toolsurface.audit import AUDIT_PREFIX, build_audit_sink
from shepherd.toolsurface.client import master_tools, withdraw_turn_approvals
from shepherd.toolsurface.compose import log_root
from shepherd.toolsurface.tools_master import autonomy_level
from shepherd.toolsurface.types import AuditSink

__all__ = [
    "MASTER_CALLER_ID",
    "MASTER_MODEL_KEY",
    "MASTER_SESSION_KEY",
    "ShutdownOutcome",
    "audit_sink",
    "build_master",
    "shut_down",
]

#: The `app_state` row holding the model this build's orchestrator runs on.
#: §17 names hard-coding the model as the mistake, and names the row the future
#: settings page will write: *"a single `app_state` row (`runtime`, `provider`,
#: `model`, `base_url`, `credential_ref`)"*. This is that row's `model`, read on
#: every build so a change takes effect at the next turn boundary (D20 rule 5).
MASTER_MODEL_KEY = "master_model"

#: What runs when nobody has chosen. A default is not a hard-coding — the
#: distinction §17 draws is whether a settings page can reach the value, and
#: `MASTER_MODEL_KEY` is the row it writes — but it is an alias rather than a
#: dated id, because a pinned `claude-…-20251001` is a value that stops
#: resolving and takes the orchestrator down with it (the defect the M4 plan
#: found in `master_probe.py`, §903).
DEFAULT_MASTER_MODEL = "sonnet"

#: Who the audit log says called. One id for the orchestrator, spelled here
#: because this is the only thing that builds one.
MASTER_CALLER_ID = "master"


def build_master(store: Store, turn_id: str) -> MasterRuntime:
    """The runtime for **one turn**, keyed on that turn (RD-T4-2).

    Called per turn by `TurnDriver`, never at boot: RD6 makes the master lazy,
    which is why `M4Wiring` carries no thread and why this process starts none.

    The four things `master/` cannot reach on its own (D19, K24) are closed over
    here: the counter, the withdrawal, the tool set and the prompt's autonomy
    level. The withdrawal is **the client's own public function**, not a private
    path — the root binds the client and hands over what it bound.

    **D10's continuity is read back here** (§T27-6): the turn driver persists
    `master_session_id` from the first event of a turn that names one, and until
    this line nothing ever read it — a conversation that was saved on every turn
    and resumed on none. A missing row resumes **nothing**, rather than resuming
    the empty string, because an id the engine has no transcript for is a lost
    resume (E-M4-8) and not a cold start.
    """
    level = int(autonomy_level(store))
    runtime = AgentSDKMaster(
        caller_id=MASTER_CALLER_ID,
        turn_id=lambda: turn_id,
        bump=lambda kind: _bump(store, kind),
        withdraw_turn_approvals=withdraw_turn_approvals,
        model=_model(store),
    )
    runtime.configure(master_tools(), orchestrator_prompt(level))
    conversation = store.get_app_state(MASTER_SESSION_KEY)
    if isinstance(conversation, str) and conversation:
        runtime.resume(conversation)
    return runtime


def audit_sink(store: Store, host: HostPlatform) -> AuditSink:
    """D8's sink, over a real `RotatingJsonlLog` under this host's log root.

    Handed to `compose_tool_surface`, which installs it **with** the gate in one
    assignment — DP13's rule that a gate with no audit log is not a state this
    build can hold. Nothing else constructs one, so "the audit log was not on"
    has no representation either.
    """
    return build_audit_sink(
        RotatingJsonlLog(log_root(host), AUDIT_PREFIX),
        lambda kind: _bump(store, kind),
        date_of,
    )


def _bump(store: Store, kind: AnomalyKind) -> None:
    """The counter `master/` and `audit.py` are handed (K24, E-M4-6).

    A named function rather than `store.bump_anomaly` itself: the store's verb
    takes the `str` the schema holds, and handing a member straight to it would
    write `AnomalyKind.MASTER_TOOL_UNEXPECTED` — the enum's repr — into a column
    every reader compares against the value.
    """
    store.bump_anomaly(str(kind.value))


def _model(store: Store) -> str:
    """§17's row, narrowed. A non-string under the key is **ignored**, not
    coerced — the same answer `compose.runner_socket` gives, and for the same
    reason: a coerced `"None"` would be a model nobody chose."""
    stored = store.get_app_state(MASTER_MODEL_KEY)
    return stored if isinstance(stored, str) and stored else DEFAULT_MASTER_MODEL
