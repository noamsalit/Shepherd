-- 003_m3_mailbox — the seventh table (M3 plan DP3).
--
-- Forward-only, and additive only: 001 and 002 are not edited, and **nothing
-- in this file touches `session`**. 002 had to rebuild `session` because SQLite
-- cannot alter a CHECK; 003 has no such need, and
-- `tests/store/test_migration_003.py` holds it to that by diffing `session`'s
-- whole column spec and both its indexes across the migration.
--
-- Exactly one thing:
--
--  1. `mailbox_message` — somewhere for a queued message to live that survives
--     a `controld` restart (D37: "restart, upgrade and crash freely").
--
-- §7 says "six tables". It enumerates the tables that existed when it was
-- written, and D12 then made the mailbox the *one* delivery path: coalesced,
-- idempotent for a retrying caller, queryable per session, and durable across a
-- restart. Every one of those is a property a table has and the alternatives do
-- not — `app_state` is a key/value row for singletons with no index and no
-- partial write; a JSON column on `session` is one row's queue rewritten whole
-- on every enqueue, and a lost update the first time two callers send at once;
-- memory loses the queue at the first upgrade, which makes D12's "one place to
-- get it right" untrue. Flagged as gap N2 against §7's count.
--
-- There is no `channel_message` table here. D12: channels are the addressing
-- layer and have **no delivery code of their own**, so the transport alone is
-- complete and M6 builds on this exactly.
--
-- No `PRAGMA foreign_key_check` trailer. 002 has one, but the runner discards
-- statement results, so it can only ever report by raising — and it cannot
-- raise here: this migration creates a table and inserts nothing, so there is
-- no reference it could invalidate. The FK that matters is proved by a test
-- that queues a message for a session that does not exist.

CREATE TABLE mailbox_message (
  id                TEXT PRIMARY KEY,                    -- ulid
  owner_id          TEXT NOT NULL DEFAULT 'local',       -- D2
  session_id        TEXT NOT NULL REFERENCES session(id),
  -- D12: "a retrying caller never double-delivers". Enforced by the unique
  -- index below rather than by a check-then-insert, which races.
  idempotency_key   TEXT NOT NULL,
  body              TEXT NOT NULL,
  -- Who queued it. `core.mailbox.MailboxOrigin` is total over exactly these
  -- five, and `test_every_mailbox_origin_is_accepted_by_the_check` proves it.
  -- Deliberately NOT `session.origin`'s list: `session` (one agent messaging
  -- another) is a sender, `ask_fork` is not.
  origin            TEXT NOT NULL CHECK (origin IN
                      ('orchestrator', 'queue_worker', 'user_ui', 'session', 'external')),
  queued_at         TEXT NOT NULL,
  -- NULL until delivered, and the row is *kept* for the retention window after
  -- it is: a deleted row is an `idempotency_key` that can be reused, so the
  -- stamp is what lets a duplicate still be refused.
  delivered_at      TEXT,
  delivery_attempts INTEGER NOT NULL DEFAULT 0,
  -- The `WriteDecision` that deferred it (§9's write policy). Principle 5 on
  -- the write path: a message that keeps deferring says **why**, on the row,
  -- and `doctor` counts them.
  last_refusal      TEXT
);

CREATE UNIQUE INDEX ux_mailbox_idem ON mailbox_message(session_id, idempotency_key);

-- `pending_for(session_id)` is the sweep's hot read, and the table keeps
-- delivered rows, so without this it scans the retention window every pass.
CREATE INDEX ix_mailbox_pending ON mailbox_message(session_id, delivered_at);
