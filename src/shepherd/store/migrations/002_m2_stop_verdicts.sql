-- 002_m2_stop_verdicts — M2's four schema changes (ADR-M2-4).
--
-- Forward-only, and the FIRST migration to run over an existing schema. M1
-- twice amended 001 in place, justified by "it has never been applied anywhere
-- but a dev database" *within that milestone*; re-litigating that here would
-- break every dev database by checksum (§7 rule 1 — refuse to start) and would
-- mean the forward-only rule had still never actually run.
--
-- Exactly four things:
--
--  1. widen `stop_reason`'s CHECK from 16 values to 20 — §8's four completeness
--     reasons (`completed`, `incomplete`, `derailed`, `blocked_external`) were
--     missing, so the classifier could not write its own answer (DP2, gap N2);
--  2. widen `decided_by`'s CHECK from 4 to 5, adding `heuristic` — a heuristic
--     verdict has to be able to say that is what it is (DP1, gap N1);
--  3. add `auto_compact_at TEXT` — the stamp of the most recent
--     `PreCompact{auto}`, cleared by a compaction finishing or by a turn
--     ending (C12's bound);
--  4. add `quota_notice_at TEXT` — the stamp of the most recent quota
--     notification, cleared by the next turn (G-M2-1).
--
-- (3) and (4) are columns because D24 discards the events that prove
-- `context_exhausted` and `quota_paused` as soon as they are folded. A mark
-- that does not persist is a rule that cannot fire after a restart.
--
-- SQLite cannot alter a CHECK, so (1) and (2) use the documented table rebuild
-- inside the one transaction `migrate()` already opens. This is the single
-- riskiest statement in M2; `tests/store/test_migration_002.py` holds it to
-- every row, every column default and both indexes.
--
-- **`PRAGMA foreign_keys=off` is a no-op inside a transaction** (SQLite
-- documents it as such), and the runner has already issued BEGIN by the time
-- these statements execute. `PRAGMA defer_foreign_keys=ON` is the form that
-- works there: enforcement is postponed to COMMIT, by which point
-- `session_new` has been renamed and every reference resolves. It resets
-- itself at COMMIT, so nothing leaks into the next connection.
PRAGMA defer_foreign_keys=ON;

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

  -- (1) twenty values: §8's sixteen mechanical reasons plus the four the
  -- completeness split produces. `core.stops.StopReason` is total over exactly
  -- this list, and `test_every_stop_reason_is_accepted_by_the_check` proves it.
  stop_reason       TEXT CHECK (stop_reason IS NULL OR stop_reason IN
                      ('rate_limited', 'quota_paused', 'auth_failed', 'account_blocked',
                       'bad_request', 'server_error', 'truncated', 'stalled_pending_tool',
                       'crashed', 'killed', 'context_exhausted', 'user_exited', 'cleared',
                       'logged_out', 'resumed_elsewhere', 'unknown',
                       'completed', 'incomplete', 'derailed', 'blocked_external')),
  -- `outcome` is deliberately NOT widened: `unclassified` is a stopped row with
  -- **no verdict**, so the column stays NULL and the bucket is derived at
  -- projection time (E-M2-4). A value written here would claim a verdict.
  outcome           TEXT CHECK (outcome IS NULL OR outcome IN
                      ('running', 'needs_you', 'finished', 'unfinished', 'blocked',
                       'paused', 'error')),
  why               TEXT,
  confidence        REAL,
  -- (2) `heuristic` — DP1. `model` and `manual` stay, and nothing at M2 writes them.
  decided_by        TEXT CHECK (decided_by IS NULL OR decided_by IN
                      ('mechanical', 'heuristic', 'model', 'declared', 'manual')),
  next_actions      TEXT NOT NULL DEFAULT '[]',
  ended_at          TEXT,
  exit_code         INTEGER,

  -- (3) and (4): the two marks D24's discard would otherwise lose.
  auto_compact_at   TEXT,
  quota_notice_at   TEXT
);

-- Every column named explicitly. A `SELECT *` here would silently depend on
-- column order surviving, which is the failure this migration exists to avoid.
INSERT INTO session_new (
  id, owner_id, engine_session_id, workspace_id, repo_id, work_item_id, work_item_ref,
  parent_session_id, origin, ownership, ephemeral, depth, retry_of, attempt, brief, cwd,
  worktree_path, runner_handle, engine, provider, model, effort, credential_ref, runner,
  started_at, title, title_source, title_synced_at, state, last_event_at, needs_you_reason,
  tasks_done, tasks_total, active_subagents, repos_touched, pr_url, observed_at,
  live_subagent_ids, created_task_ids, completed_task_ids, pid, proc_start, stop_reason,
  outcome, why, confidence, decided_by, next_actions, ended_at, exit_code
)
SELECT
  id, owner_id, engine_session_id, workspace_id, repo_id, work_item_id, work_item_ref,
  parent_session_id, origin, ownership, ephemeral, depth, retry_of, attempt, brief, cwd,
  worktree_path, runner_handle, engine, provider, model, effort, credential_ref, runner,
  started_at, title, title_source, title_synced_at, state, last_event_at, needs_you_reason,
  tasks_done, tasks_total, active_subagents, repos_touched, pr_url, observed_at,
  live_subagent_ids, created_task_ids, completed_task_ids, pid, proc_start, stop_reason,
  outcome, why, confidence, decided_by, next_actions, ended_at, exit_code
FROM session;

DROP TABLE session;

-- Renaming rewrites `session_new`'s own self-references to `session`.
ALTER TABLE session_new RENAME TO session;

CREATE INDEX ix_session_fleet ON session(workspace_id, state);

CREATE UNIQUE INDEX ux_session_engine_id
  ON session(engine_session_id) WHERE engine_session_id IS NOT NULL;

PRAGMA foreign_key_check;
