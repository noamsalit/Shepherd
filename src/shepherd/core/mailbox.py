"""The mailbox vocabulary — D12's one delivery path, typed once, at L1 (T3).

`store/mailbox.py`, `orchestration/mailbox.py` and `toolsurface/` import
**downward** into this module and none defines a second copy (the F9 /
BLOCKER-T7b-1 lesson). Types, enums, frozen dataclasses and constants only —
no SQL, no driver, no clock (ADR-7, the storage boundary).

The row these types mirror is migration 003's `mailbox_message`, the seventh
table: §7 enumerates six because it was written before the mailbox was built,
and every property D12 asks of it — survive a `controld` restart, refuse a
duplicate `idempotency_key`, coalesce at delivery, be queryable per session —
is a property a table has and `app_state`, a JSON column and memory do not
(**DP3**, gap N2).

`owner_id` is deliberately not a field: D2's default is `'local'` and the
column carries it, so a single-user caller never passes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: Migration 003's table name, written once rather than in five SQL literals.
MAILBOX_TABLE = "mailbox_message"

#: D12: "five queued notes become one message with five bullets". The trailing
#: space is part of the bullet — without it the write renders as `-ship it`.
COALESCE_BULLET = "- "


class MailboxOrigin(StrEnum):
    """Who queued the message.

    **Not `core.states.Origin`.** That enum answers "how did this *session*
    start" and has `ask_fork`; this one answers "who is writing to it" and has
    `session` — one agent messaging another (§9's channels fan out to these
    rows, D12). Migration 003's `CHECK` lists exactly these five.
    """

    ORCHESTRATOR = "orchestrator"
    QUEUE_WORKER = "queue_worker"
    USER_UI = "user_ui"
    SESSION = "session"
    EXTERNAL = "external"


@dataclass(frozen=True)
class MailboxMessage:
    """One row of `mailbox_message` (D33 rule 2 — never a driver row).

    Frozen because delivery *reads* the pending set and writes through the
    store: a mutable message would let a coalescing reader edit a row the store
    still owns, and the edit would silently not be persisted. `delivered_at`
    and `last_refusal` are `None` rather than `""`, so "never delivered" stays
    a different fact from "delivered at an unknown time" (principle 5).
    `last_refusal` is the `WriteDecision` that deferred this message — one that
    keeps deferring says **why**, on the row, and `doctor` counts them.
    """

    id: str
    session_id: str
    idempotency_key: str
    body: str
    origin: MailboxOrigin
    queued_at: str
    delivered_at: str | None
    delivery_attempts: int
    last_refusal: str | None


@dataclass(frozen=True)
class MailboxCounts:
    """What one sweep did, and what `doctor` prints (T14, T20).

    `deferred` is not `pending - delivered`: it is a pending message the write
    policy refused *this* pass, and collapsing the two would hide the session
    that is never writable.
    """

    pending: int
    delivered: int
    deferred: int
