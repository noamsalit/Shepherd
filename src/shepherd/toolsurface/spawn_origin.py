"""Who asked -> the `origin` a spawn is recorded under (§7, D31).

**D1 of the M1-M4 QA pass.** `tools_m3` held one module-level constant,
`Origin.USER_UI`, and every spawn through the tool surface wrote it — the
master's included. `store/reads.py::WAKE_ORIGIN` is `Origin.ORCHESTRATOR`, so
`wake_candidates` selected a set **nothing in `src/` could ever put a row into**:
D31's wake set was structurally empty in production, and every test of it passed
because each one wrote its own `origin=orchestrator` row directly.

`spawn_session` is one registered capability serving a person clicking the fleet
page *and* the master, so the origin has to follow **who asked**. `invoke()` now
hands the handler the `CallerContext` it has already validated
(`types.Handler`), and this module is what that context is read through.

**Keyed on `ActorKind`, not `Audience`.** M5's queue worker arrives on the
`MASTER` audience and is not the master (DP2, K23), and D31 routes a
queue-spawned stop to the worker loop rather than to the master's wake set — so
keying on the audience would put every worker's session in the wake set the day
M5 lands. `actor_kind_of` is the one derivation and it is imported, never
re-spelled.

**The master's row is `admission.MASTER_ORIGIN`, imported.** That constant and
the wake query were the only two mentions of `Origin.ORCHESTRATOR` in `src/`, and
neither was a write; a third spelling here would be a third thing to keep in step
with a value whose whole job is that two modules agree on it.

**`SESSION` stays at `USER_UI`, and that is a decision.** A tier-2 session's
spawn is none of §7's five origins cleanly, and moving it would be a spec
question about D31's lineage rather than a repair. This module moves only the
rows D31 names, and the unchanged row is written out rather than defaulted so it
is as visible as the changed ones.
"""

from __future__ import annotations

from collections.abc import Mapping

from shepherd.core.states import Origin
from shepherd.orchestration.admission import MASTER_ORIGIN
from shepherd.toolsurface.types import ActorKind, CallerContext, actor_kind_of

__all__ = ["SPAWN_ORIGIN_BY_ACTOR", "spawn_origin"]

#: Total over `ActorKind`. `test_the_origin_map_is_total_over_every_actor_kind_
#: and_only_the_master_wakes` enumerates the enum at test time, so a fifth member
#: is a failing build here rather than a `KeyError` raised inside a spawn that
#: has already started a pane.
SPAWN_ORIGIN_BY_ACTOR: Mapping[ActorKind, Origin] = {
    ActorKind.MASTER: MASTER_ORIGIN,
    ActorKind.WORKER: Origin.QUEUE_WORKER,
    ActorKind.HUMAN: Origin.USER_UI,
    ActorKind.SESSION: Origin.USER_UI,
}


def spawn_origin(ctx: CallerContext) -> Origin:
    """The origin this caller's spawn is recorded under. One lookup, one site."""
    return SPAWN_ORIGIN_BY_ACTOR[actor_kind_of(ctx)]
