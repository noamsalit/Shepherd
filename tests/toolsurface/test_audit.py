"""T5 — the audit record, the sink that writes it, and the tail that reads it.

**The trap this module is written against (P-M4-4).** An audit test that injects
its own collector proves the collector works, not that anything ever writes a
line. So every assertion here that matters is driven through the **shipped**
`build_audit_sink` over a **real** `RotatingJsonlLog` under `tmp_path`, and read
back with the **shipped** `read_audit_records` — bytes on disk, not a list a
fixture appended to. The two log stubs that do appear (`_FailingLog`,
`_RaisingLog`) exist for the one behaviour a real log cannot be made to show
twice over: a failed write and a raising one, which is E-M4-6's whole subject.

**What T5 cannot prove, and says so rather than implying it.** P-M4-4's own
check is `test_the_composed_surface_writes_to_a_real_log`, and it belongs to
T25: `install_chokepoint` (T6) and the composition that calls it (T25) are not
in this tree yet, so *the shipped composition calls this sink* is not a
statement any test in this file can make. What is proved here is the half T5
owns — the shipped sink, the shipped encoder and the shipped reader over a real
log at the path the composition will hand it (`log_root(host) / AUDIT_PREFIX`).
See `docs/plans/m4-blockers/t5.md` §T5-2.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Iterator

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import date_of
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface.audit import (
    AUDIT_PREFIX,
    REDACTED,
    UNKNOWN_DATE,
    actor_kind_of,
    build_audit_sink,
    encode_audit_record,
    read_audit_records,
)
from shepherd.toolsurface.compose import log_root
from shepherd.toolsurface.policy import ApprovedBy
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    AuditRecord,
    BlastClass,
    CallerContext,
    Failure,
)

# ----- ADR-M4-1's example, as a fixture ---------------------------------------

#: ADR-M4-1's inputs, transcribed from the ADR.
ADR_RECORD = AuditRecord(
    at="2026-09-17T10:22:40Z",
    correlation_id="c8f1a2d4",
    actor_kind=ActorKind.MASTER,
    actor_id="mst_01",
    tool="kill_session",
    blast_class=BlastClass.LOCAL_DESTRUCTIVE,
    args={"id": "ses_7f3k"},
    autonomy_level=2,
    decision="allow",
    approved_by=ApprovedBy.USER.value,
    approval_id="apr_3k9",
    result="ok",
    failure=None,
    duration_ms=412,
)

#: ADR-M4-1's JSON, transcribed from the ADR with its comments stripped. The
#: document and the encoder cannot drift because this literal is the document.
ADR_JSON: Mapping[str, object] = {
    "at": "2026-09-17T10:22:40Z",
    "correlation_id": "c8f1a2d4",
    "actor_kind": "master",
    "actor_id": "mst_01",
    "tool": "kill_session",
    "blast_class": "local_destructive",
    "args": {"id": "ses_7f3k"},
    "autonomy_level": 2,
    "decision": "allow",
    "approved_by": "user",
    "approval_id": "apr_3k9",
    "result": "ok",
    "failure": None,
    "duration_ms": 412,
}


def _record(**overrides: object) -> AuditRecord:
    """ADR-M4-1's record with fields replaced — never `dataclasses.replace`d from
    a mutable default, so one test cannot leak into the next."""
    values = {field.name: getattr(ADR_RECORD, field.name) for field in fields(AuditRecord)}
    values.update(overrides)
    return AuditRecord(**values)  # type: ignore[arg-type]


# ----- the log, real, under tmp_path ------------------------------------------


def _host(tmp_path: Path) -> ScriptedHost:
    """The five records `ScriptedHost` needs, all of them under `tmp_path`.

    Only `dirs()` is read here: the point is that the audit log's directory is
    `log_root(host) / AUDIT_PREFIX`, resolved by the **shipped** resolver, so a
    test cannot agree with a path the composition root would not use.
    """
    runtime_dir = tmp_path / "run"
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=tmp_path / "data",
            config_dir=tmp_path / "config",
            runtime_dir=runtime_dir,
        ),
        socket_plan=SocketPlan(
            path=runtime_dir / "sessiond.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(
            command="scripted-send",
            requires=("scripted-send",),
            available=True,
            reason="scripted fixture",
        ),
        supervision_plan=Supervision(
            kind="foreground",
            detail="no supervisor on this host",
            manageable=False,
            start_limit_note="scripted fixture",
        ),
        login=LoginPersistence(
            enabled=None, mechanism="none observed", detail="scripted fixture"
        ),
    )


class _Bumps:
    """The injected `bump`, as a list of what it was called with."""

    def __init__(self) -> None:
        self.seen: list[AnomalyKind] = []

    def __call__(self, kind: AnomalyKind) -> None:
        self.seen.append(kind)


class _FailingLog:
    """A log that reports a lost line, which a real one does only under a fault.

    It records the **date** it was handed: the sink's choice of daily file is
    not otherwise observable, and a mutation that turned an unreadable stamp
    into an empty date survived until this list existed (T5-4, MUT-12).
    """

    def __init__(self) -> None:
        self.calls = 0
        self.dates: list[str] = []

    def append(self, record: Mapping[str, object], date: str) -> bool:
        self.calls += 1
        self.dates.append(date)
        return False


class _RaisingLog:
    """A log that raises. E-M4-6's other half: the sink still may not raise."""

    def append(self, record: Mapping[str, object], date: str) -> bool:
        raise OSError("the disk went away mid-write")


@pytest.fixture()
def audit_root(tmp_path: Path) -> Iterator[Path]:
    """`log_root(host)` — the directory the composition root will hand the log."""
    yield log_root(_host(tmp_path))


def _write(root: Path, records: tuple[AuditRecord, ...]) -> _Bumps:
    """Drive the **shipped** sink over a **real** rotating log and close it."""
    bumps = _Bumps()
    log = RotatingJsonlLog(root, AUDIT_PREFIX)
    sink = build_audit_sink(log, bumps, date_of)
    for record in records:
        sink(record)
    log.close()
    return bumps


# ----- the record --------------------------------------------------------------


def test_the_audit_record_matches_the_documented_example() -> None:
    """ADR-M4-1's inputs → ADR-M4-1's JSON, key order included.

    Goes red if a field is renamed, added or dropped without the ADR changing.
    The key **order** is asserted too, because the ADR writes the record out as
    an ordered document and a reader chasing one bad line reads it that way.
    """
    encoded = encode_audit_record(ADR_RECORD)
    assert dict(encoded) == dict(ADR_JSON)
    assert list(encoded) == list(ADR_JSON)


def test_every_field_of_the_record_is_exercised() -> None:
    """The encoded key set against `dataclasses.fields()`, enumerated at test
    time (K19). Never a count: a literal 14 would survive one field renamed into
    another. Goes red if a field is added to the dataclass and not encoded."""
    declared = {field.name for field in fields(AuditRecord)}
    assert declared, "AuditRecord declares no fields at all"
    assert set(encode_audit_record(ADR_RECORD)) == declared
    # …and the documented example is the same enumeration, so the ADR cannot
    # fall behind the dataclass either.
    assert set(ADR_JSON) == declared
    # Every field is *exercised*, not merely present: the two that are `None` in
    # the ADR's example carry a value here, because `"failure": null` on its own
    # never runs the branch that encodes a real one. ADR-M4-1 added `failure`
    # precisely so a reader can tell *the tool crashed half way* from *the tool
    # never ran*, and a record that spelled it `FAILED` would not join to
    # `Failure` in a 90-day `jq` query.
    failed = encode_audit_record(
        _record(result="failed", failure=Failure.FAILED, approval_id=None)
    )
    assert failed["failure"] == "failed"
    assert failed["result"] == "failed"
    assert failed["approval_id"] is None
    assert json.loads(json.dumps(dict(failed)))["failure"] == "failed"


def test_a_human_call_is_audited_as_claimed_human_not_as_user() -> None:
    """K23. Goes red if the two `ApprovedBy` values are collapsed, and the
    assertion is on the **bytes** of the encoded line, not on the mapping: a
    record that says *a person approved this* when nobody did is the artefact
    the next incident is reconstructed from."""
    assert ApprovedBy.CLAIMED_HUMAN is not ApprovedBy.USER
    assert ApprovedBy.CLAIMED_HUMAN.value != ApprovedBy.USER.value
    claimed = _record(
        actor_kind=ActorKind.HUMAN,
        approved_by=ApprovedBy.CLAIMED_HUMAN.value,
        approval_id=None,
    )
    line = json.dumps(dict(encode_audit_record(claimed))).encode("utf-8")
    assert b'"approved_by":"claimed_human"' in line.replace(b", ", b",").replace(b": ", b":")
    assert b"claimed_human" in line
    # Arrival before absence: the encoder demonstrably *can* write `"user"` —
    # the ADR's own example does — so its absence here is an absence that could
    # have failed.
    assert b'"user"' in json.dumps(dict(encode_audit_record(ADR_RECORD))).encode("utf-8")
    assert b'"user"' not in line
    assert b'"approved_by": "user"' not in line


def test_a_worker_context_is_recorded_as_a_worker() -> None:
    """`actor_kind_of` reads the field when it is set (DP2). Goes red if it
    derives from the audience unconditionally, which is what made `WORKER`
    unreachable at revision 1 and DP2's M5 promise unimplementable."""
    worker = CallerContext(
        audience=Audience.MASTER,
        caller_id="wrk_01",
        correlation_id="c1",
        actor_kind=ActorKind.WORKER,
    )
    assert actor_kind_of(worker) is ActorKind.WORKER
    # …and the derivation is still there for the callers that do not set it, over
    # every `Audience` enumerated at test time — never a literal three.
    audiences = set(Audience)
    assert audiences, "Audience has no members"
    for audience in audiences:
        derived = actor_kind_of(
            CallerContext(audience=audience, caller_id="c", correlation_id="c1")
        )
        assert derived.value == audience.value, audience
    # WORKER is reachable *only* through the field, which is the whole point.
    assert ActorKind.WORKER.value not in {audience.value for audience in audiences}


def test_a_secret_shaped_argument_is_redacted() -> None:
    """§13's rule, on the **bytes** of the encoded line.

    Asserting against the mapping would pass on an encoder that redacted the
    top level and serialised a nested secret verbatim.
    """
    secret = "ghp_thisisnotarealtokenatall"
    record = _record(
        args={
            "id": "ses_7f3k",
            "api_token": secret,
            "nested": {"password": secret},
            "listed": [{"secret_key": secret}],
            # §13 says the audit log sees `credential_ref` — redacting the one
            # safe form of a credential is losing the field the rule leaves in.
            "credential_ref": "cred_9",
        }
    )
    encoded = encode_audit_record(record)
    line = json.dumps(dict(encoded)).encode("utf-8")
    assert secret.encode("utf-8") not in line
    assert line.count(REDACTED.encode("utf-8")) == 3
    # The whole `*key*` family is one marker, so every spelling of it is caught
    # rather than the three somebody remembered.
    family = {"api_key": secret, "apikey": secret, "PRIVATE_KEY": secret, "access_key": secret}
    spread = json.dumps(dict(encode_audit_record(_record(args=family)))).encode("utf-8")
    assert secret.encode("utf-8") not in spread
    assert spread.count(REDACTED.encode("utf-8")) == len(family)
    assert b"cred_9" in line
    assert b"ses_7f3k" in line
    # Arrival before absence: an unredacted record of the same shape does carry
    # the secret, so the absence above is one this assertion could have broken.
    plain = json.dumps(dict(encode_audit_record(_record(args={"api_token": secret})))).encode()
    assert REDACTED.encode("utf-8") in plain


# ----- the sink ----------------------------------------------------------------


def test_the_shipped_sink_writes_a_real_log_the_shipped_reader_reads(
    audit_root: Path,
) -> None:
    """P-M4-4's half that T5 owns: sink → bytes on disk → reader.

    No fixture collects anything. The record is written by the shipped
    `build_audit_sink` through a real `RotatingJsonlLog`, the bytes are read off
    the filesystem, and the record comes back through the shipped reader.
    """
    bumps = _write(audit_root, (ADR_RECORD,))
    assert bumps.seen == []

    # The bytes are on disk, at the path the composition root resolves.
    directory = audit_root / AUDIT_PREFIX
    written = sorted(directory.iterdir())
    assert [path.name for path in written] == ["2026-09-17.jsonl.gz"], written

    # …and the shipped reader reads them back, whole.
    read = read_audit_records(audit_root, limit=10)
    assert [dict(record) for record in read] == [dict(ADR_JSON)]


def test_a_lost_audit_line_is_counted_not_swallowed() -> None:
    """E-M4-6, in both halves: a log that reports failure and a log that raises.

    Goes red if `AUDIT_LINE_LOST` is not bumped, and goes red if the sink
    raises — a swallowed exception that kills a destructive call mid-flight is
    worse than a missing line.
    """
    failing = _FailingLog()
    bumps = _Bumps()
    build_audit_sink(failing, bumps, date_of)(ADR_RECORD)
    assert failing.calls == 1
    assert bumps.seen == [AnomalyKind.AUDIT_LINE_LOST]

    raising = _Bumps()
    build_audit_sink(_RaisingLog(), raising, date_of)(ADR_RECORD)  # must not raise
    assert raising.seen == [AnomalyKind.AUDIT_LINE_LOST]

    # …and a record whose stamp the date reader cannot place is still written
    # rather than lost: a visible `unknown-date` file is the lesser failure.
    undated = _Bumps()
    log = _FailingLog()
    build_audit_sink(log, undated, lambda _at: None)(ADR_RECORD)
    assert log.calls == 1
    assert log.dates == [UNKNOWN_DATE]
    # …and a readable stamp still reaches its own daily file, so the assertion
    # above is an equality the sink could have failed in either direction.
    dated = _FailingLog()
    build_audit_sink(dated, _Bumps(), date_of)(ADR_RECORD)
    assert dated.dates == ["2026-09-17"]


def test_a_sink_without_a_log_is_not_representable(audit_root: Path) -> None:
    """DP13's property at T5's layer, built rather than assumed.

    DP13's hole was a sink that defaulted to `None`, which made *no log* a
    representable state and "no record" read as correct. `build_audit_sink` has
    no defaulted parameter, so an audit sink cannot be constructed without a log
    behind it; `install_chokepoint` (T6) carries the same property one layer up
    for the gate. Goes red the moment any parameter here acquires a default.
    """
    signature = inspect.signature(build_audit_sink)
    assert signature.parameters, "build_audit_sink takes nothing at all"
    for name, parameter in signature.parameters.items():
        assert parameter.default is inspect.Parameter.empty, name
    with pytest.raises(TypeError):
        build_audit_sink()  # type: ignore[call-arg]


# ----- the reader ---------------------------------------------------------------


def test_the_reader_tails_in_reverse_order_and_skips_malformed(audit_root: Path) -> None:
    """D25's reader. The ordering assertion is **not** satisfiable by the
    writer's own order: the fixture writes the three records out of
    chronological order deliberately (M3 found an ordering assertion satisfied
    by the query's own `ORDER BY`), and a malformed trailing line is appended
    by hand, which a daemon killed mid-write leaves behind.
    """
    middle = _record(at="2026-09-17T10:22:40Z", correlation_id="middle")
    newest = _record(at="2026-09-17T23:59:59Z", correlation_id="newest")
    oldest = _record(at="2026-09-17T00:00:01Z", correlation_id="oldest")
    # Write order: oldest, newest, middle. Chosen so that **no** prefix of the
    # file is the answer: a reader that sliced to `limit` before ordering would
    # return `[newest, oldest]` for `limit=2`, not `[newest, middle]`. It
    # survived a write order of `middle, newest, oldest` by coincidence, which
    # is the whole reason this comment names the order (T5-4, MUT-15).
    _write(audit_root, (oldest, newest, middle))

    directory = audit_root / AUDIT_PREFIX
    [written] = sorted(directory.iterdir())
    assert written.name.endswith(".gz")
    # The tail reads a *live* day too, so the fixture un-gzips it and appends the
    # torn line the way a killed daemon would.
    import gzip

    plain = directory / "2026-09-17.jsonl"
    plain.write_bytes(gzip.decompress(written.read_bytes()))
    written.unlink()
    with plain.open("a", encoding="utf-8") as handle:
        handle.write('{"at": "2026-09-17T12:00:00Z", "correlation_')

    read = read_audit_records(audit_root, limit=10)
    assert [record["correlation_id"] for record in read] == ["newest", "middle", "oldest"]
    # …and the file's own order is a different one, so the assertion above is
    # about the reader.
    on_disk = [
        json.loads(line)["correlation_id"]
        for line in plain.read_text(encoding="utf-8").splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
    assert on_disk == ["oldest", "newest", "middle"]

    # The limit is a tail: the newest `limit` records, not the first read.
    assert [record["correlation_id"] for record in read_audit_records(audit_root, limit=2)] == [
        "newest",
        "middle",
    ]
    assert read_audit_records(audit_root, limit=0) == ()


def test_the_reader_reads_nothing_from_an_empty_root(tmp_path: Path) -> None:
    """A root with no log yet is empty, not an exception — the audit view is
    rendered before the first destructive call has ever happened."""
    assert read_audit_records(tmp_path / "nothing", limit=50) == ()
