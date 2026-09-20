"""T3 — the mailbox vocabulary (DP3).

Unit seam: `core/mailbox.py` is types, enums and constants only, so every check
here is a value check. The half of T3 that needs a database — that the `CHECK`
constraint and `MailboxOrigin` are one vocabulary — lives in
`tests/store/test_migration_003.py`, against a real SQLite file.

Expected values are literals taken from the plan's *Produces* block, never
derived from the module under test: a test that reads `MailboxOrigin` to build
its own expectation agrees with any rename.
"""

from __future__ import annotations

import dataclasses

import pytest

from shepherd.core.mailbox import (
    COALESCE_BULLET,
    MAILBOX_TABLE,
    MailboxCounts,
    MailboxMessage,
    MailboxOrigin,
)


def a_message(**overrides: object) -> MailboxMessage:
    fields: dict[str, object] = {
        "id": "01MSG",
        "session_id": "01SESSION",
        "idempotency_key": "k-1",
        "body": "ship it",
        "origin": MailboxOrigin.ORCHESTRATOR,
        "queued_at": "2026-09-17T00:00:00Z",
        "delivered_at": None,
        "delivery_attempts": 0,
        "last_refusal": None,
    }
    fields.update(overrides)
    return MailboxMessage(**fields)  # type: ignore[arg-type]


def test_mailbox_origin_is_exactly_the_five_spellings_the_check_lists() -> None:
    """The enum and migration 003's `CHECK` are one vocabulary or neither is.

    Goes red on a sixth member added without widening the `CHECK` — the write
    that fails at 3 a.m. on the first message from the new origin — and on a
    renamed value, e.g. `session` drifting to `agent`.
    """
    assert {origin.value for origin in MailboxOrigin} == {
        "orchestrator",
        "queue_worker",
        "user_ui",
        "session",
        "external",
    }


def test_mailbox_origin_is_not_session_origin() -> None:
    """§7 `session.origin` has `ask_fork` and no `session`; the mailbox is the
    other way round. Goes red if someone "unifies" the two enums — a fork would
    then be a legal message sender and `session` an illegal one."""
    from shepherd.core.states import Origin

    assert {origin.value for origin in MailboxOrigin} != {origin.value for origin in Origin}
    assert "ask_fork" not in {origin.value for origin in MailboxOrigin}


def test_a_queued_message_cannot_be_mutated_in_place() -> None:
    """D12 coalescing reads the pending rows; a mutable message would let a
    reader edit a row the store still owns. Goes red if `frozen=True` is lost."""
    message = a_message()
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.body = "something else"  # type: ignore[misc]


def test_a_message_carries_every_column_the_row_has_except_the_owner() -> None:
    """Goes red if a field is added to the table and not to the type (or vice
    versa) — the mismatch that makes `rows.mailbox_message()` silently drop a
    column. `owner_id` is deliberately absent: it is D2's single-user default."""
    assert [field.name for field in dataclasses.fields(MailboxMessage)] == [
        "id",
        "session_id",
        "idempotency_key",
        "body",
        "origin",
        "queued_at",
        "delivered_at",
        "delivery_attempts",
        "last_refusal",
    ]


def test_an_undelivered_message_says_so_with_nulls_not_with_sentinels() -> None:
    """Principle 5: a message that has never been delivered has no stamp and no
    refusal. Goes red if either becomes `""`, which would read as delivered."""
    message = a_message()
    assert message.delivered_at is None
    assert message.last_refusal is None
    assert message.delivery_attempts == 0


def test_a_deferred_message_says_why_on_the_row() -> None:
    """DP3's "`last_refusal` is what makes principle 5 true of the write path"."""
    deferred = a_message(last_refusal="session_busy", delivery_attempts=3)
    assert deferred.last_refusal == "session_busy"
    assert deferred.delivery_attempts == 3
    assert deferred.delivered_at is None


def test_mailbox_counts_has_the_three_buckets_doctor_prints() -> None:
    counts = MailboxCounts(pending=2, delivered=5, deferred=1)
    assert (counts.pending, counts.delivered, counts.deferred) == (2, 5, 1)
    assert [field.name for field in dataclasses.fields(MailboxCounts)] == [
        "pending",
        "delivered",
        "deferred",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        counts.pending = 99  # type: ignore[misc]


def test_the_table_name_is_written_once() -> None:
    """`store/mailbox.py` (T4) builds its SQL against this name. Goes red on a
    rename that migration 003 did not make."""
    assert MAILBOX_TABLE == "mailbox_message"


def test_the_coalesce_bullet_is_a_markdown_bullet_with_its_space() -> None:
    """D12: five queued notes become one message with five bullets. A bullet
    without the trailing space renders as `-ship it`; goes red if it is lost."""
    assert COALESCE_BULLET == "- "
