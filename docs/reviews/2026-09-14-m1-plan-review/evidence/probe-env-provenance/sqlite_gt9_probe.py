"""Scratch probe: test every SQLite behaviour asserted in plan Ground Truth 9 and the
Codebase Reality Check row, plus the plan's own 0001 DDL run through its stated migration
algorithm. Run: python3 sqlite_gt9_probe.py <plan.md>. Uses only temp files."""
import os, re, sqlite3, subprocess, sys, tempfile, time, textwrap, signal

PLAN = sys.argv[1]
results = []
def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")

print("python", sys.version.split()[0], "sqlite", sqlite3.sqlite_version)
tmp = tempfile.mkdtemp(prefix="shp-sqlprobe-")

def conn(path=":memory:"):
    c = sqlite3.connect(path, isolation_level=None)
    return c

# GT9.1 FULL OUTER JOIN
c = conn()
c.execute("create table a(x)"); c.execute("create table b(x)")
c.execute("insert into a values (1),(2)"); c.execute("insert into b values (2),(3)")
try:
    rows = sorted(c.execute("select a.x, b.x from a full outer join b on a.x=b.x").fetchall(), key=str)
    rec("GT9.1 FULL OUTER JOIN", len(rows) == 3, str(rows))
except Exception as e:
    rec("GT9.1 FULL OUTER JOIN", False, repr(e))

# GT9.2 ALTER TABLE ADD COLUMN with CHECK, enforced; NOT NULL DEFAULT '[]' CHECK(json_valid) ; on STRICT table with rows
c = conn()
c.execute("create table s(id TEXT PRIMARY KEY, v INTEGER) STRICT")
c.execute("insert into s values ('a',1)")
try:
    c.execute("alter table s add column outcome TEXT CHECK (outcome IS NULL OR outcome IN ('done','blocked'))")
    c.execute("alter table s add column next_actions TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(next_actions) AND json_type(next_actions)='array')")
    existing = c.execute("select outcome, next_actions from s").fetchall()
    enforced1 = enforced2 = False
    try: c.execute("update s set outcome='bogus'")
    except sqlite3.IntegrityError: enforced1 = True
    try: c.execute("update s set next_actions='not json'")
    except sqlite3.IntegrityError: enforced2 = True
    rec("GT9.2 ADD COLUMN CHECK on STRICT w/ rows, enforced", enforced1 and enforced2, f"existing={existing} enum_enforced={enforced1} json_enforced={enforced2}")
except Exception as e:
    rec("GT9.2 ADD COLUMN CHECK", False, repr(e))
# extra: ADD COLUMN whose CHECK fails for existing rows' default
try:
    c.execute("alter table s add column bad TEXT NOT NULL DEFAULT 'x' CHECK (bad <> 'x')")
    rec("extra: ADD COLUMN whose default violates CHECK is refused", False, "accepted")
except Exception as e:
    rec("extra: ADD COLUMN whose default violates CHECK is refused", True, repr(e))

# GT9.3 DDL inside BEGIN..ROLLBACK rolls back
c = conn()
c.execute("BEGIN IMMEDIATE"); c.execute("create table t(x)"); c.execute("insert into t values(1)"); c.execute("ROLLBACK")
n = c.execute("select count(*) from sqlite_master where name='t'").fetchone()[0]
rec("GT9.3 DDL rollback", n == 0, f"sqlite_master rows for t after rollback={n}")

# GT9.4 foreign_keys=ON, FK references missing table, NULL value insert fails
c = conn(); c.execute("PRAGMA foreign_keys=ON")
c.execute("create table child(id TEXT PRIMARY KEY, wi TEXT REFERENCES work_item(id)) STRICT")
for label, val in (("NULL", None), ("non-NULL", "x")):
    try:
        c.execute("insert into child values (?,?)", (label, val))
        rec(f"GT9.4 FK->missing table, insert {label} fails", False, "insert succeeded")
    except Exception as e:
        rec(f"GT9.4 FK->missing table, insert {label} fails", True, repr(e))
c2 = conn(); c2.execute("PRAGMA foreign_keys=OFF")
c2.execute("create table child(id TEXT PRIMARY KEY, wi TEXT REFERENCES work_item(id)) STRICT")
try:
    c2.execute("insert into child values ('a',NULL)"); rec("control: FK->missing table with foreign_keys=OFF inserts", True, "ok")
except Exception as e:
    rec("control: FK->missing table with foreign_keys=OFF inserts", False, repr(e))

# GT9.5 executescript issues implicit COMMIT (test in the plan's own mode: isolation_level=None + explicit BEGIN)
for mode in ("isolation_level=None", "default isolation_level", "autocommit=False"):
    p = os.path.join(tmp, f"es_{mode.split('=')[0]}.db")
    if mode == "isolation_level=None":
        c = sqlite3.connect(p, isolation_level=None); c.execute("BEGIN")
    elif mode == "autocommit=False":
        c = sqlite3.connect(p, autocommit=False)
    else:
        c = sqlite3.connect(p)
    c.execute("create table pre(x)")
    c.execute("insert into pre values (1)")
    in_tx_before = c.in_transaction
    try:
        c.executescript("create table post(y);")
        in_tx_after = c.in_transaction
        # see if rollback undoes 'pre'
        try: c.execute("ROLLBACK")
        except Exception as e: pass
        other = sqlite3.connect(p)
        pre_visible = other.execute("select count(*) from sqlite_master where name='pre'").fetchone()[0]
        rec(f"GT9.5 executescript implicit COMMIT [{mode}]", pre_visible == 1,
            f"in_tx before={in_tx_before} after={in_tx_after}; 'pre' survives ROLLBACK={bool(pre_visible)}")
    except Exception as e:
        rec(f"GT9.5 executescript [{mode}]", False, repr(e))

# Reality-check row: partial unique index + ON CONFLICT(col) WHERE ... DO NOTHING, changes() 1 then 0
c = conn()
c.execute("create table ses(id TEXT PRIMARY KEY, esid TEXT) STRICT")
c.execute("create unique index ux on ses(esid) where esid is not null")
q = "insert into ses(id, esid) values (?, ?) on conflict(esid) where esid is not null do nothing"
c.execute(q, ("a", "E1")); ch1 = c.execute("select changes()").fetchone()[0]
c.execute(q, ("b", "E1")); ch2 = c.execute("select changes()").fetchone()[0]
c.execute(q, ("c", None)); c.execute(q, ("d", None)); nulls = c.execute("select count(*) from ses where esid is null").fetchone()[0]
rec("RC partial unique idx + ON CONFLICT WHERE DO NOTHING", (ch1, ch2) == (1, 0), f"changes {ch1} then {ch2}; NULL esid rows allowed={nulls}")
# same without the WHERE on the conflict target (plan requires it)
try:
    c.execute("insert into ses(id, esid) values ('e','E1') on conflict(esid) do nothing")
    rec("extra: ON CONFLICT(esid) without WHERE against partial index", False, "accepted (WHERE not needed)")
except Exception as e:
    rec("extra: ON CONFLICT(esid) without WHERE against partial index is an error", True, repr(e))

# RC: STRICT type enforcement + json funcs + GLOB time CHECK
c = conn()
c.execute("create table w(ts TEXT NOT NULL CHECK (length(ts)=24 AND ts GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z'), n INTEGER) STRICT")
ok_ins = True
try: c.execute("insert into w values ('2026-09-14T10:00:00.000Z', 1)")
except Exception: ok_ins = False
bad_ts = False
try: c.execute("insert into w values ('2026-09-14T10:00:00Z', 1)")
except sqlite3.IntegrityError: bad_ts = True
strict = False
try: c.execute("insert into w values ('2026-09-14T10:00:00.000Z', 'abc')")
except sqlite3.IntegrityError: strict = True
jt = c.execute("select json_valid('[]'), json_type('[]'), json_valid('x')").fetchone()
rec("RC STRICT + GLOB ts CHECK + json funcs", ok_ins and bad_ts and strict and jt == (1, 'array', 0), f"good_ts_ok={ok_ins} bad_ts_rejected={bad_ts} strict_rejects_text_in_int={strict} json={jt}")

# Plan S1: extract 0001 DDL verbatim and run it through the stated runner algorithm
text = open(PLAN, encoding="utf-8").read()
m = re.search(r"`0001_foundation\.sql`:\s*```sql\n(.*?)```", text, re.S)
sm = re.search(r"```sql\n(CREATE TABLE IF NOT EXISTS schema_migration.*?)```", text, re.S)
ddl = m.group(1); smddl = sm.group(1)
open(os.path.join(tmp, "0001_foundation.sql"), "w").write(ddl)
dbp = os.path.join(tmp, "shep.db")
c = sqlite3.connect(dbp, isolation_level=None)
wal = c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
c.execute("PRAGMA synchronous=NORMAL"); c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=5000")
stmts, buf = [], ""
for line in ddl.splitlines(keepends=True):
    buf += line
    if sqlite3.complete_statement(buf):
        stmts.append(buf); buf = ""
leftover = buf.strip()
try:
    c.execute("BEGIN IMMEDIATE")
    c.execute(smddl)
    for s in stmts:
        c.execute(s)
    c.execute("insert into schema_migration values (1,'foundation','x','2026-09-14T10:00:00.000Z')")
    fkc = c.execute("PRAGMA foreign_key_check").fetchall()
    c.execute("COMMIT")
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
    rec("S1 0001 DDL via complete_statement splitter in BEGIN IMMEDIATE", True,
        f"wal={wal} statements={len(stmts)} leftover={leftover[:80]!r} fk_check={fkc} tables={tables}")
except Exception as e:
    rec("S1 0001 DDL via runner", False, repr(e) + f" statements={len(stmts)}")
    try: c.execute("ROLLBACK")
    except Exception: pass

# S1 behaviour: attached session insert shape (DV-30) + partial-index upsert on real table
try:
    now = "2026-09-14T10:00:00.000Z"
    q = ("insert into session(id, engine_session_id, workspace_id, origin, ownership, cwd, engine, started_at, state, last_event_at) "
         "values (?,?,?,?,?,?,?,?,?,?) on conflict(engine_session_id) where engine_session_id is not null do nothing")
    c.execute("BEGIN IMMEDIATE")
    c.execute(q, ("ses_1", "E1", "wsp_unassigned", "external", "attached", "/w", "claude_code", now, "stopped", now)); a = c.execute("select changes()").fetchone()[0]
    c.execute(q, ("ses_2", "E1", "wsp_unassigned", "external", "attached", "/w", "claude_code", now, "stopped", now)); b = c.execute("select changes()").fetchone()[0]
    c.execute("COMMIT")
    rec("S1 register_attached_session upsert on real DDL", (a, b) == (1, 0), f"changes {a},{b}")
except Exception as e:
    rec("S1 register_attached_session upsert on real DDL", False, repr(e))
    try: c.execute("ROLLBACK")
    except Exception: pass

# S1: needs_you invariant CHECK
try:
    c.execute("update session set state='needs_you' where id='ses_1'")
    rec("S1 needs_you invariant CHECK rejects missing reason", False, "accepted")
except sqlite3.IntegrityError as e:
    rec("S1 needs_you invariant CHECK rejects missing reason", True, repr(e))

# DV-10 forward-compat: M2 ADD COLUMN the six stop-group columns on the real session table with a row present
try:
    c.execute("BEGIN IMMEDIATE")
    for col in ("stop_reason TEXT", "outcome TEXT CHECK (outcome IS NULL OR outcome IN ('done','partial','blocked','failed','unknown'))",
                "why TEXT", "confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))",
                "decided_by TEXT CHECK (decided_by IS NULL OR decided_by IN ('mechanical','heuristic','declared','manual'))",
                "next_actions TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(next_actions) AND json_type(next_actions) = 'array')"):
        c.execute(f"ALTER TABLE session ADD COLUMN {col}")
    fkc = c.execute("PRAGMA foreign_key_check").fetchall()
    c.execute("COMMIT")
    rej = False
    try: c.execute("update session set confidence=2 where id='ses_1'")
    except sqlite3.IntegrityError: rej = True
    rec("DV-10 M2 ADD COLUMN x6 on real STRICT session table", rej, f"fk_check={fkc} confidence CHECK enforced={rej} row={c.execute('select next_actions from session').fetchone()}")
except Exception as e:
    rec("DV-10 M2 ADD COLUMN x6", False, repr(e))
    try: c.execute("ROLLBACK")
    except Exception: pass

# DV-11: what would happen if work_item_id had REFERENCES work_item(id) (confirm the reason for the deviation on the real schema)
c3 = sqlite3.connect(":memory:", isolation_level=None); c3.execute("PRAGMA foreign_keys=ON")
ddl_fk = ddl.replace("work_item_id      TEXT,", "work_item_id      TEXT REFERENCES work_item(id),")
buf = ""
for line in ddl_fk.splitlines(keepends=True):
    buf += line
    if sqlite3.complete_statement(buf): c3.execute(buf); buf = ""
try:
    c3.execute("insert into session(id, workspace_id, origin, ownership, cwd, started_at, state) values ('ses_x','wsp_unassigned','external','attached','/w','2026-09-14T10:00:00.000Z','stopped')")
    rec("DV-11 real DDL + FK to missing work_item: NULL insert fails", False, "insert succeeded")
except Exception as e:
    rec("DV-11 real DDL + FK to missing work_item: NULL insert fails", True, repr(e))

# SIGKILL mid-migration leaves old state (T05 claim), process started by this script
dbk = os.path.join(tmp, "kill.db")
child = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
import sqlite3,time
c=sqlite3.connect({dbk!r}, isolation_level=None)
c.execute('PRAGMA journal_mode=WAL')
c.execute('BEGIN IMMEDIATE')
c.execute('create table half(x)')
c.execute('insert into half values (1)')
print('ready', flush=True)
time.sleep(30)
""")], stdout=subprocess.PIPE, text=True)
child.stdout.readline(); os.kill(child.pid, signal.SIGKILL); child.wait()
k = sqlite3.connect(dbk); n = k.execute("select count(*) from sqlite_master where name='half'").fetchone()[0]
rec("T05 SIGKILL mid-DDL transaction leaves no table (WAL)", n == 0, f"child rc={child.returncode} half tables={n}")

print("\nSUMMARY", sum(1 for r in results if r[1]), "pass /", len(results))
