-- 005_refused_stop_reason — `refused`, the 21st stop reason (§3 D73, ADR-QR-6).
--
-- Forward-only. Exactly one thing: widen `stop_reason`'s CHECK from 20 values
-- to 21 by appending `refused`. A start the runner refuses ends its pre-written
-- row with that verdict (owner ruling 9, BC-28) instead of leaving it live, and
-- `core.stops.StopReason` is total over exactly this list. Every other column,
-- CHECK, default and index is 002's, byte for byte.
--
-- SQLite cannot alter a CHECK, so `session` is rebuilt the way 002 did it,
-- inside the one transaction `migrate()` already opens. **002's pattern alone
-- no longer works.** Since 003, `mailbox_message.session_id REFERENCES
-- session(id)` (`003:37`), and that is the only reference into `session` from
-- outside it (`project_repo` names `workspace` and `repo` only). With foreign
-- keys on, `DROP TABLE session` runs an implicit DELETE, every mailbox row it
-- orphans bumps the deferred-violation counter, and the rename does not un-bump
-- it: the rehearsal over the real 001 to 004 with mailbox rows failed at COMMIT
-- with `FOREIGN KEY constraint failed`. So the mailbox rows are stashed in a
-- TEMP table and deleted first, `session` is rebuilt, and they are put back.
-- `mailbox_message` itself is never dropped, so its two indexes are untouched.
-- `tests/store/test_migration_005.py` holds this to every row and cell of both
-- tables, and keeps a negative control proving the stash is load-bearing.
--
-- Not `PRAGMA writable_schema` with a text replace on `sqlite_master`, which
-- also passed the rehearsal: SQLite documents it as able to corrupt the file,
-- it is refused under SQLITE_DBCONFIG_DEFENSIVE, and a string edit of stored
-- schema text goes silently wrong the day that text differs. A forward-only
-- migration on the owner's real database is the wrong place for it.
--
-- `PRAGMA foreign_keys=off` is a no-op inside a transaction, so deferral is the
-- form that works here, kept for the two self-references (`parent_session_id`,
-- `retry_of`). It resets itself at COMMIT. No trigger, and no string literal
-- holding a semicolon or a comment marker: the runner splits on semicolons.
PRAGMA defer_foreign_keys=ON;

CREATE TEMP TABLE mailbox_stash AS SELECT
  id, owner_id, session_id, idempotency_key, body, origin, queued_at, delivered_at,
  delivery_attempts, last_refusal
FROM mailbox_message;

DELETE FROM mailbox_message;

CREATE TABLE session_new (
  id                TEXT PRIMARY KEY,
  owner_id          TEXT NOT NULL DEFAULT 'local',
  engine_session_id TEXT,
  workspace_id      TEXT NOT NULL REFERENCES workspace(id),
  repo_id           TEXT REFERENCES repo(id),
  work_item_id      TEXT,
  work_item_ref     TEXT,
  parent_session_id TEXT REFERENCES session_new(id),
  origin            TEXT NOT NULL CHECK (origin IN
                      ('orchestrator', 'queue_worker', 'user_ui', 'external', 'ask_fork')),
  ownership         TEXT NOT NULL CHECK (ownership IN ('owned', 'attached')),
  ephemeral         INTEGER NOT NULL DEFAULT 0 CHECK (ephemeral IN (0, 1)),
  depth             INTEGER NOT NULL DEFAULT 0,
  retry_of          TEXT REFERENCES session_new(id),
  attempt           INTEGER NOT NULL DEFAULT 1,
  brief             TEXT,
  cwd               TEXT,
  worktree_path     TEXT,
  runner_handle     TEXT,
  engine            TEXT NOT NULL,
  provider          TEXT,
  model             TEXT,
  effort            TEXT,
  credential_ref    TEXT,
  runner            TEXT,
  started_at        TEXT NOT NULL,

  title             TEXT,
  title_source      TEXT NOT NULL DEFAULT 'brief'
                      CHECK (title_source IN ('user', 'engine', 'brief')),
  title_synced_at   TEXT,

  state             TEXT NOT NULL CHECK (state IN
                      ('starting', 'running', 'needs_you', 'stopped')),
  last_event_at     TEXT,
  needs_you_reason  TEXT,
  tasks_done        INTEGER NOT NULL DEFAULT 0,
  tasks_total       INTEGER NOT NULL DEFAULT 0,
  active_subagents  INTEGER NOT NULL DEFAULT 0,
  repos_touched     TEXT NOT NULL DEFAULT '[]',
  pr_url            TEXT,

  observed_at         TEXT,
  live_subagent_ids   TEXT NOT NULL DEFAULT '[]',
  created_task_ids    TEXT NOT NULL DEFAULT '[]',
  completed_task_ids  TEXT NOT NULL DEFAULT '[]',

  pid               INTEGER,
  proc_start        TEXT,

  -- twenty-one values: 002's twenty, then `refused` (D73), the one reason a
  -- spawn declares rather than a stop capture producing it.
  stop_reason       TEXT CHECK (stop_reason IS NULL OR stop_reason IN
                      ('rate_limited', 'quota_paused', 'auth_failed', 'account_blocked',
                       'bad_request', 'server_error', 'truncated', 'stalled_pending_tool',
                       'crashed', 'killed', 'context_exhausted', 'user_exited', 'cleared',
                       'logged_out', 'resumed_elsewhere', 'unknown',
                       'completed', 'incomplete', 'derailed', 'blocked_external',
                       'refused')),
  outcome           TEXT CHECK (outcome IS NULL OR outcome IN
                      ('running', 'needs_you', 'finished', 'unfinished', 'blocked',
                       'paused', 'error')),
  why               TEXT,
  confidence        REAL,
  decided_by        TEXT CHECK (decided_by IS NULL OR decided_by IN
                      ('mechanical', 'heuristic', 'model', 'declared', 'manual')),
  next_actions      TEXT NOT NULL DEFAULT '[]',
  ended_at          TEXT,
  exit_code         INTEGER,

  auto_compact_at   TEXT,
  quota_notice_at   TEXT
);

-- All 52 columns named on both sides. A `SELECT *` would silently depend on
-- column order surviving, which is the failure a rebuild exists to avoid.
INSERT INTO session_new (
  id, owner_id, engine_session_id, workspace_id, repo_id, work_item_id, work_item_ref,
  parent_session_id, origin, ownership, ephemeral, depth, retry_of, attempt, brief, cwd,
  worktree_path, runner_handle, engine, provider, model, effort, credential_ref, runner,
  started_at, title, title_source, title_synced_at, state, last_event_at, needs_you_reason,
  tasks_done, tasks_total, active_subagents, repos_touched, pr_url, observed_at,
  live_subagent_ids, created_task_ids, completed_task_ids, pid, proc_start, stop_reason,
  outcome, why, confidence, decided_by, next_actions, ended_at, exit_code,
  auto_compact_at, quota_notice_at
)
SELECT
  id, owner_id, engine_session_id, workspace_id, repo_id, work_item_id, work_item_ref,
  parent_session_id, origin, ownership, ephemeral, depth, retry_of, attempt, brief, cwd,
  worktree_path, runner_handle, engine, provider, model, effort, credential_ref, runner,
  started_at, title, title_source, title_synced_at, state, last_event_at, needs_you_reason,
  tasks_done, tasks_total, active_subagents, repos_touched, pr_url, observed_at,
  live_subagent_ids, created_task_ids, completed_task_ids, pid, proc_start, stop_reason,
  outcome, why, confidence, decided_by, next_actions, ended_at, exit_code,
  auto_compact_at, quota_notice_at
FROM session;

DROP TABLE session;

-- Renaming rewrites `session_new`'s own self-references to `session`.
ALTER TABLE session_new RENAME TO session;

CREATE INDEX ix_session_fleet ON session(workspace_id, state);

CREATE UNIQUE INDEX ux_session_engine_id
  ON session(engine_session_id) WHERE engine_session_id IS NOT NULL;

-- The stash goes back only now, so every row resolves against the new table.
INSERT INTO mailbox_message (
  id, owner_id, session_id, idempotency_key, body, origin, queued_at, delivered_at,
  delivery_attempts, last_refusal
)
SELECT
  id, owner_id, session_id, idempotency_key, body, origin, queued_at, delivered_at,
  delivery_attempts, last_refusal
FROM mailbox_stash;

DROP TABLE mailbox_stash;
