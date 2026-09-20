"""Extract Spec S1 DDL verbatim from the plan, apply it with the plan's own runner algorithm
(line accumulation + sqlite3.complete_statement, no executescript), then probe constraints and
compare columns against the S4 Session dataclass and the spec's section 7 column list."""
import re, sqlite3, tempfile, os
P = "/root/Shepherd/docs/plans/2026-09-13-m1-foundation-visibility-plan.md"
t = open(P).read()
s1 = t[t.index("## Spec S1"):t.index("## Spec S2")]
blocks = re.findall(r"```sql\n(.*?)```", s1, re.S)
mig_table, foundation = blocks[0], blocks[1]
print("sqlite", sqlite3.sqlite_version)
d = tempfile.mkdtemp(); db = os.path.join(d, "x.db")
c = sqlite3.connect(db, isolation_level=None)
c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON")
c.execute("BEGIN IMMEDIATE")
c.execute(mig_table)
buf, stmts = "", []
for line in foundation.splitlines(keepends=True):
    buf += line
    if sqlite3.complete_statement(buf):
        stmts.append(buf); buf = ""
print("statements:", len(stmts), "leftover non-empty:", repr(buf.strip())[:80])
for st in stmts: c.execute(st)
print("fk_check rows:", c.execute("PRAGMA foreign_key_check").fetchall())
c.execute("COMMIT")
print("tables:", [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")])
print("indexes (explicit):", [r[0] for r in c.execute("select name from sqlite_master where type='index' and sql is not null order by name")])
print("indexes (all incl autoindex):", [r[0] for r in c.execute("select name from sqlite_master where type='index' order by name")])
cols = [r[1] for r in c.execute("PRAGMA table_info(session)")]
print("session columns:", len(cols))
reg = t[t.index("class Session:"):t.index("class SessionLivePatch")]
fields = re.findall(r"([a-z_]+):\s", reg.split("\n",1)[1])
print("Session dataclass fields:", len(fields))
print("  in DDL not dataclass:", sorted(set(cols)-set(fields)))
print("  in dataclass not DDL:", sorted(set(fields)-set(cols)))
print("  same order:", cols == fields)
now = "2026-09-14T10:00:00.000Z"
def tryx(label, sql, *a):
    try:
        c.execute(sql, a); print("OK  ", label)
    except Exception as e:
        print("FAIL", label, "->", type(e).__name__, e)
base = ("INSERT INTO session(id,workspace_id,origin,ownership,cwd,started_at,state,last_event_at) VALUES (?,?,?,?,?,?,?,?)")
tryx("attached at-prompt insert", base, "ses_1","wsp_unassigned","external","attached","/w",now,"stopped",now)
tryx("upsert ON CONFLICT partial idx", "INSERT INTO session(id,engine_session_id,workspace_id,origin,ownership,cwd,started_at,state) VALUES ('ses_2','e1','wsp_unassigned','external','attached','/w',?, 'stopped') ON CONFLICT(engine_session_id) WHERE engine_session_id IS NOT NULL DO NOTHING", now)
print("   changes", c.execute("select changes()").fetchone())
tryx("upsert dup", "INSERT INTO session(id,engine_session_id,workspace_id,origin,ownership,cwd,started_at,state) VALUES ('ses_3','e1','wsp_unassigned','external','attached','/w',?, 'stopped') ON CONFLICT(engine_session_id) WHERE engine_session_id IS NOT NULL DO NOTHING", now)
print("   changes", c.execute("select changes()").fetchone())
# fold contract: SessionStart{compact} on a needs_you session -> state stays needs_you, reason := None
tryx("set needs_you with reason", "UPDATE session SET state='needs_you', needs_you_reason='permission: Bash(x)' WHERE id='ses_1'")
tryx("SessionStart(compact) on needs_you per contract 1: reason:=None, state unchanged", "UPDATE session SET needs_you_reason=NULL, ended_at=NULL WHERE id='ses_1'")
tryx("time GLOB on workspace.created_at bad", "INSERT INTO workspace(id,name,created_at) VALUES ('wsp_x','x','2026-09-14T10:00:00Z')")
tryx("session.started_at 24 chars non-ISO accepted? (only length checked)", base, "ses_9","wsp_unassigned","external","attached","/w","xxxxxxxxxxxxxxxxxxxxxxxx","stopped",None)
tryx("repo root trailing slash rejected", "INSERT INTO workspace(id,name,created_at) VALUES ('wsp_a','a',?)", now)
tryx("repo root_path '/a/' ", "INSERT INTO repo(id,workspace_id,name,root_path,added_at) VALUES ('rep_1','wsp_a','a','/a/',?)", now)
tryx("M2 ADD COLUMN with CHECK on STRICT", "ALTER TABLE session ADD COLUMN next_actions TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(next_actions))")
