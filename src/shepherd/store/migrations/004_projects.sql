-- 004_projects — a project becomes a declared object with a lifecycle (§3 D57).
--
-- Rehearsed against the real 001->003 schema with real rows before the plan was
-- written: applies clean, `PRAGMA foreign_key_check` empty, both delete paths
-- work. Three decisions are worth reading before the statements:
--
--  * **`session` is never rebuilt.** The obvious reading of D61 -- "delete
--    cascades to sessions" -- suggests `ON DELETE CASCADE` on
--    `session.workspace_id`, and SQLite cannot ALTER a foreign key, so that
--    would mean rebuilding a 50-column table the way 002 did. It buys nothing:
--    the verb must offer kill / orphan / cancel before anything is deleted, so
--    the verb runs regardless, and a schema-level cascade makes any future
--    accidental `DELETE FROM workspace` destroy session rows silently. The
--    cascade lives in the verb, ordered
--    `mailbox_message -> session -> project_repo -> workspace`.
--  * **`DROP COLUMN` on `repo.workspace_id` succeeds** even though it is the
--    FK-*referencing* side. That was assumed to fail and the assumption was
--    wrong -- probed on SQLite 3.45.1. So `repo` is not rebuilt either, and
--    `tests/store/test_migration_004.py` asserts the host is >= 3.35 so the
--    probe's answer applies wherever this runs.
--  * **The seeded `unassigned` row omits `owner_id`**, so `001:30`'s
--    `NOT NULL DEFAULT 'local'` applies. Writing `'local'` here would make this
--    file a second definition site of a value the schema already owns.
--
-- `PRAGMA foreign_keys=off` is a no-op inside a transaction and the runner has
-- already issued BEGIN, so this is the form that works here -- copied from
-- `002:37` rather than re-derived. It resets itself at COMMIT.
PRAGMA defer_foreign_keys=ON;

ALTER TABLE workspace ADD COLUMN description TEXT;

CREATE TABLE project_repo (
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  repo_id      TEXT NOT NULL REFERENCES repo(id),
  added_at     TEXT NOT NULL,
  PRIMARY KEY (workspace_id, repo_id)
);

-- The backfill, before the column it reads is dropped. `added_at` is copied
-- rather than stamped now: the repo joined its project when the repo row was
-- written, and that already happened.
INSERT INTO project_repo (workspace_id, repo_id, added_at)
  SELECT workspace_id, id, added_at FROM repo;

ALTER TABLE repo DROP COLUMN workspace_id;

ALTER TABLE workspace DROP COLUMN root_path;

-- D48 makes `git_common_dir` the binding key and `find_repo_by_common_dir` is a
-- full table scan today (`reads.py:74-76`). Cheap, and the table is open anyway.
CREATE INDEX ix_repo_common_dir ON repo(git_common_dir);

-- The reserved project (ADR-P2). A literal id rather than a ULID: a sentinel
-- that reads as itself in a log beats one nobody can recognise. Seeded by the
-- migration so `session.workspace_id NOT NULL` is satisfiable from the first
-- moment a session can be orphaned.
INSERT INTO workspace (id, name, description, created_at)
  VALUES ('unassigned', 'Unassigned', 'Work that matched no declared project.',
          '1970-01-01T00:00:00Z');
