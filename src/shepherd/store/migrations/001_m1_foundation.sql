-- 001_m1_foundation — M1's four tables plus the schema's own bookkeeping (§7).
--
-- Scope notes, each one a deliberate decision rather than an omission:
--
--  * `work_item` and `queue` arrive at M5. `session.work_item_id` and
--    `session.work_item_ref` exist as columns because §7 lists them, but carry
--    **no foreign key**: their target table does not exist yet.
--  * `session.pid` / `session.proc_start` are the plan's Decision pressure 7
--    (M13). C13 records their absence as the limitation that keeps `crashed`
--    and `stopped` apart; the sidecar that holds both is deleted on exit (E29),
--    so without these columns the hookless path can never set `ended_at`.
--    Written only by the registry path, read only by the liveness sweep.
--  * `repo.git_common_dir` is D48's binding key
--    (`git rev-parse --path-format=absolute --git-common-dir`). A linked
--    worktree is a *sibling* of the repo, so longest-prefix matching of `cwd`
--    returns null for exactly the sessions that need binding.
--  * Every table carries `owner_id TEXT NOT NULL DEFAULT 'local'` (D2). Times
--    are TEXT ISO-8601 UTC. Enums are TEXT with a CHECK constraint, never ints.
--    JSON columns hold only what is read back whole.

CREATE TABLE schema_migration (
  version    INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  checksum   TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE workspace (
  id               TEXT PRIMARY KEY,
  owner_id         TEXT NOT NULL DEFAULT 'local',
  name             TEXT NOT NULL,
  root_path        TEXT,
  created_at       TEXT NOT NULL,
  last_activity_at TEXT
);

CREATE TABLE repo (
  id             TEXT PRIMARY KEY,
  owner_id       TEXT NOT NULL DEFAULT 'local',
  workspace_id   TEXT NOT NULL REFERENCES workspace(id),
  name           TEXT NOT NULL,
  root_path      TEXT NOT NULL,
  git_common_dir TEXT,
  vcs_remote     TEXT,
  active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  added_at       TEXT NOT NULL
);

CREATE TABLE session (
  -- written once at spawn
  id                TEXT PRIMARY KEY,
  owner_id          TEXT NOT NULL DEFAULT 'local',
  engine_session_id TEXT,
  workspace_id      TEXT NOT NULL REFERENCES workspace(id),
  repo_id           TEXT REFERENCES repo(id),
  work_item_id      TEXT,
  work_item_ref     TEXT,
  parent_session_id TEXT REFERENCES session(id),
  origin            TEXT NOT NULL CHECK (origin IN
                      ('orchestrator', 'queue_worker', 'user_ui', 'external', 'ask_fork')),
  ownership         TEXT NOT NULL CHECK (ownership IN ('owned', 'attached')),
  ephemeral         INTEGER NOT NULL DEFAULT 0 CHECK (ephemeral IN (0, 1)),
  depth             INTEGER NOT NULL DEFAULT 0,
  retry_of          TEXT REFERENCES session(id),
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

  -- §7.1 title subsystem
  title             TEXT,
  title_source      TEXT NOT NULL DEFAULT 'brief'
                      CHECK (title_source IN ('user', 'engine', 'brief')),
  title_synced_at   TEXT,

  -- overwritten continuously while alive: this group *is* the event store (D24)
  state             TEXT NOT NULL CHECK (state IN
                      ('starting', 'running', 'needs_you', 'stopped')),
  last_event_at     TEXT,
  needs_you_reason  TEXT,
  tasks_done        INTEGER NOT NULL DEFAULT 0,
  tasks_total       INTEGER NOT NULL DEFAULT 0,
  active_subagents  INTEGER NOT NULL DEFAULT 0,
  repos_touched     TEXT NOT NULL DEFAULT '[]',
  pr_url            TEXT,

  -- the fold's own prior state (BLOCKER-T6-1, T7b-5, T11-4; plan gap M16).
  -- `observed_at` is RD8's per-field recency key: without it the two writer
  -- lanes resolve by write order and the registry always looks newer than the
  -- hook. The three id sets are what subagent pairing and the `tasks_done`
  -- intersection are computed from, so without a column a `controld` restart
  -- silently resets them and an in-flight subagent's stop becomes an anomaly
  -- that is not one. JSON arrays, read back whole, never queried into.
  observed_at         TEXT,
  live_subagent_ids   TEXT NOT NULL DEFAULT '[]',
  created_task_ids    TEXT NOT NULL DEFAULT '[]',
  completed_task_ids  TEXT NOT NULL DEFAULT '[]',

  -- liveness inputs that outlive the sidecar (Decision pressure 7)
  pid               INTEGER,
  proc_start        TEXT,

  -- written at stop, overwritten when a rule improves
  stop_reason       TEXT CHECK (stop_reason IS NULL OR stop_reason IN
                      ('rate_limited', 'quota_paused', 'auth_failed', 'account_blocked',
                       'bad_request', 'server_error', 'truncated', 'stalled_pending_tool',
                       'crashed', 'killed', 'context_exhausted', 'user_exited', 'cleared',
                       'logged_out', 'resumed_elsewhere', 'unknown')),
  outcome           TEXT CHECK (outcome IS NULL OR outcome IN
                      ('running', 'needs_you', 'finished', 'unfinished', 'blocked',
                       'paused', 'error')),
  why               TEXT,
  confidence        REAL,
  decided_by        TEXT CHECK (decided_by IS NULL OR decided_by IN
                      ('mechanical', 'model', 'declared', 'manual')),
  next_actions      TEXT NOT NULL DEFAULT '[]',
  ended_at          TEXT,
  exit_code         INTEGER
);

CREATE TABLE app_state (
  key        TEXT PRIMARY KEY,
  owner_id   TEXT NOT NULL DEFAULT 'local',
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_repo_path ON repo(root_path);
CREATE INDEX ix_session_fleet ON session(workspace_id, state);

-- P14 by construction: one `session` row per engine session id, while §7's
-- "null until the engine emits it" stays legal.
CREATE UNIQUE INDEX ux_session_engine_id
  ON session(engine_session_id) WHERE engine_session_id IS NOT NULL;
