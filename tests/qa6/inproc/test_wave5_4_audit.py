"""Wave 5, INP #1: M16 — audit records are complete, include denials, and state the level (C-4, C-20).

Runs after the turns and wake modules in the same process (file order), so the
audit file already holds M3's approval (`user`), M4's reject (deny, `null`),
M6's withdrawal (`withdrawn`), M7's level-3 call (`policy`) and every HUMAN
call (`claimed_human`). The records are read with the product's own
`scan_records` (plain and gzipped day parts — the UTC day can roll mid-run),
decoded into insertion-ordered dicts, because the key *order* is part of the
oracle; the secret check reads the files' decompressed text.

The level in force is known to this module only coarsely (M7, M8, M9, M12 and
M14 flip it to 3 and back), so the `autonomy_level` clause asserts the value is
a level at all (2 or 3) on every row; the product writes a constant 0
(registry.py `UNREPORTED_AUTONOMY_LEVEL`), which is the predicted FAIL.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..httpclient import as_dict, as_list
from ..inp import Inp
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Blocked, Recorder
from .test_wave5_1_support import Master, anomaly, audit_file_view, kill_http, open_master, post, spawn_user

#: test-plan M16, verbatim and in order.
KEY_ORDER = ["at", "correlation_id", "actor_kind", "actor_id", "tool", "blast_class", "args", "autonomy_level",
             "decision", "approved_by", "approval_id", "result", "failure", "duration_ms"]
SECRET = "QA6-SECRET-VALUE"


@pytest.fixture(scope="module")
def a(inp: Inp, qa6_run: RunContext) -> Iterator[Master]:
    master = open_master(inp, qa6_run, "A16")
    try:
        yield master
    finally:
        master.stream.close()


@scenario("M16")
def test_m16_audit_records_are_complete_include_denials_and_state_the_level(a: Master, rec: Recorder) -> None:
    sid = spawn_user(a, "QA6 M16 target")
    sent = post(a, f"/api/sessions/{sid}/send", {"body": "QA6 M16", "idempotency_key": SECRET})
    rec.equal("given.secret_send_200", 200, sent.status)
    kill_http(a, sid)
    records, text = audit_file_view(a.audit.root)
    if not records:
        raise Blocked(f"M16: no audit records under {a.audit.root}")
    rec.record("files.record_count", len(records))
    misordered = [list(r) for r in records if list(r) != KEY_ORDER]
    rec.check("files.keys_exactly_in_order", not misordered, KEY_ORDER, misordered[:2])
    denials = {(r.get("tool"), r.get("approved_by")) for r in records if r.get("decision") == "deny"}
    if not any(r.get("decision") in ("allow", "deny") and r.get("actor_kind") == "master" for r in records):
        rec.block("given.earlier_master_rows", "no master rows: M16 reads the audit file after M3/M4/M6/M7 in this process")
    rec.check("files.deny_for_reject", ("kill_session", None) in denials, "a deny row for reject (approved_by null)",
              sorted(map(str, denials)))
    rec.check("files.deny_for_withdraw", ("kill_session", "withdrawn") in denials, "a deny row for withdraw (withdrawn)",
              sorted(map(str, denials)))
    allowed = {r.get("approved_by") for r in records if r.get("decision") == "allow"}
    rec.check("files.allow_user_policy_claimed_human", {"user", "policy", "claimed_human"} <= allowed,
              "allow rows with user, policy and claimed_human", sorted(map(str, allowed)))
    levels = sorted({str(r.get("autonomy_level")) for r in records})
    rec.check("files.autonomy_level_is_the_level_in_force", all(r.get("autonomy_level") in (2, 3) for r in records),
              "autonomy_level 2 or 3 (the level in force) on every row", levels)
    rec.check("files.secret_never_written", SECRET not in text, f"{SECRET!r} appears nowhere in the file",
              "present" if SECRET in text else "absent")
    tail = a.client.get("/api/audit").data()
    rows = [as_dict(r) for r in as_list(tail.get("records"))]
    stamps = [str(r.get("at")) for r in rows]
    rec.check("api.audit_newest_first_50", len(rows) == 50 and stamps == sorted(stamps, reverse=True),
              "50 rows by default, newest first", (len(rows), stamps[:3]))
    zero = a.client.get("/api/audit?limit=0").data()
    rec.equal("api.limit_zero_empty", [], zero.get("records"))
    rec.equal("api.audit_line_lost_zero", 0, anomaly(a, "audit_line_lost"))
    rec.finish()
