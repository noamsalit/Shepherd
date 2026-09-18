"""The gate: §11's blast-radius table as one pure, total function (D8, D42, DP2).

`decide()` is a function of three enum values and nothing else. No clock, no
registry, no I/O — `test_the_gate_reads_no_clock_and_no_registry` reads this
file's AST and says so, in both the import and the call spelling.

**Why a table and not a chain of `if`s.** No `external`-class tool is registered
at M4 (DP11 / G-M4-7): every one of them is a connector tool or a work-item
tool, which arrive at M4.5 and M5. A gate written as branches and proved by
walking the registry would therefore pass without ever evaluating its own
`external` row — a check reporting success without checking, in the one function
this milestone is about. Written as a table, the domain is enumerable, and
`test_the_gate_is_total_over_the_enumerated_product` compares `set(TABLE)` to
`itertools.product(set(BlastClass), set(AutonomyLevel), set(Audience))` built at
test time. Adding a member to any of the three enums is then a **failing build**
rather than a silent fall-through to whichever branch happened to be last.

**The `HUMAN` column is DP2's, and its attribution is K23's.** A human-audience
call is allowed without a card, because `authorize()` exists to bound what an
agent does *on your behalf* (D40) and a human clicking `[Kill]` is not acting on
anyone's behalf — and because blocking one would mean teaching `cli/` to render
an approval, which D38.1 forbids in the sentence that created those tools. But
`Audience.HUMAN` is an **unauthenticated self-stamp**: `web/server.py:230,299`
and `cli/main.py:164` each construct a `CallerContext` claiming it and nothing
proves it. So the attribution is `CLAIMED_HUMAN` — *a caller claimed HUMAN and
policy allowed it* — and never `USER`, which this module cannot produce at all.
`USER` means a person pressed Approve on a card, and only `approvals.py` is in a
position to know that. A log saying *a person approved this* when nobody did is
worse than no log: it is the artefact the next incident is reconstructed from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from shepherd.toolsurface.types import Audience, BlastClass


class AutonomyLevel(IntEnum):
    """D8's toggle. Two levels, and a third is a Decision, not an addition:
    level 2 acts freely on the fleet and confirms anything that leaves the
    machine; level 3 auto-approves. Level 3 is *auto-approved*, never
    *unlogged*."""

    LEVEL_2 = 2
    LEVEL_3 = 3


class Verdict(StrEnum):
    """What the gate answers. `ASK` raises a card and blocks the caller (T4);
    there is no `DENY` here, because a denial is the *outcome of an ask*, not a
    thing the table can reach on its own."""

    ALLOW = "allow"
    ASK = "ask"


class ApprovedBy(StrEnum):
    """Who or what let the call through — K23, and the first two are never
    merged."""

    POLICY = "policy"
    """The blast class allowed it outright, or level 3 did."""

    CLAIMED_HUMAN = "claimed_human"
    """The caller stamped `HUMAN` and policy allowed it. **No card was raised and
    no person was asked.** The stamp is unauthenticated, so this value claims
    exactly as much as the process knows and no more."""

    USER = "user"
    """A person pressed Approve on a card. Never produced here — `decide()`
    cannot know it, and `TABLE` is asserted not to contain it."""

    TIMEOUT = "timeout"
    """Nobody answered within `APPROVAL_TIMEOUT_S`. A denial with a reason the
    agent can act on."""

    WITHDRAWN = "withdrawn"
    """The request the approval belonged to went away (D54). Distinct from
    `TIMEOUT` because *nobody was still listening* and *nobody answered in time*
    are different facts, and an approval that outlived its turn is the case D54
    exists to name."""


@dataclass(frozen=True)
class Decision:
    """One cell of the table. `approved_by` is `None` exactly when the verdict is
    `ASK`: nothing has approved it yet, and the value it eventually carries —
    `USER`, `TIMEOUT` or `WITHDRAWN` — is decided past this module."""

    verdict: Verdict
    approved_by: ApprovedBy | None


#: §11's ten minutes, as a value the caller passes on rather than a clock this
#: module reads. The purity map's row for `decide()` is what makes the table a
#: proof, so the deadline lives here as a number and is turned into a time by
#: whoever owns a clock (T4).
APPROVAL_TIMEOUT_S: float = 600.0

#: The audiences DP2's asymmetry turns on: a caller acting *on someone's behalf*.
#: Everything that is not `HUMAN`, and the test asserts it that way rather than
#: against this literal, so a fourth audience joins the card side by default —
#: which is the safe direction for a set that decides who gets asked.
AGENT_AUDIENCES: frozenset[Audience] = frozenset({Audience.MASTER, Audience.SESSION})

_ALLOW_BY_POLICY = Decision(verdict=Verdict.ALLOW, approved_by=ApprovedBy.POLICY)
_ALLOW_AS_CLAIMED_HUMAN = Decision(verdict=Verdict.ALLOW, approved_by=ApprovedBy.CLAIMED_HUMAN)
_ASK = Decision(verdict=Verdict.ASK, approved_by=None)

#: §11's blast-radius table, one row per `(class, level, audience)`. Written out
#: rather than computed: a comprehension over the same product the test
#: enumerates would make the totality assertion tautological, and this table's
#: whole job is to be a second, independent statement of the domain.
TABLE: Mapping[tuple[BlastClass, AutonomyLevel, Audience], Decision] = {
    # `local_read` — §11: allow at both levels. `policy` is the whole reason.
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_2, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_2, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_2, Audience.HUMAN): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_3, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_3, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_READ, AutonomyLevel.LEVEL_3, Audience.HUMAN): _ALLOW_BY_POLICY,
    # `local_write` — §11: allow at both levels.
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_2, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_2, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_2, Audience.HUMAN): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_3, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_3, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_WRITE, AutonomyLevel.LEVEL_3, Audience.HUMAN): _ALLOW_BY_POLICY,
    # `local_destructive` — §11: ask at level 2, allow at level 3. DP2's row is
    # the `HUMAN` one: allowed without a card, attributed to the *claim* (K23).
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_2, Audience.MASTER): _ASK,
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_2, Audience.SESSION): _ASK,
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_2, Audience.HUMAN): _ALLOW_AS_CLAIMED_HUMAN,
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_3, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_3, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.LOCAL_DESTRUCTIVE, AutonomyLevel.LEVEL_3, Audience.HUMAN): _ALLOW_AS_CLAIMED_HUMAN,
    # `external` — §11, same shape. No tool carries this class at M4 (DP11),
    # which is exactly why the row is written here rather than walked for.
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_2, Audience.MASTER): _ASK,
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_2, Audience.SESSION): _ASK,
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_2, Audience.HUMAN): _ALLOW_AS_CLAIMED_HUMAN,
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_3, Audience.MASTER): _ALLOW_BY_POLICY,
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_3, Audience.SESSION): _ALLOW_BY_POLICY,
    (BlastClass.EXTERNAL, AutonomyLevel.LEVEL_3, Audience.HUMAN): _ALLOW_AS_CLAIMED_HUMAN,
}


def decide(
    blast_class: BlastClass, autonomy_level: AutonomyLevel, audience: Audience
) -> Decision:
    """The gate. Total over the three enums by construction — a key the table
    does not hold raises `KeyError` here rather than falling through to a
    permissive default, and the totality check is what keeps that from ever
    happening at runtime."""
    return TABLE[(blast_class, autonomy_level, audience)]
