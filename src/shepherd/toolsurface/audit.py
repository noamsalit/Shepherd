"""D25's audit log: the record (ADR-M4-1), the sink that writes it, the tail
that reads it — and the **one** `toolsurface` module permitted to import
`shepherd.logs` (DP3, P-M4-6).

**Why this module exists here and not one layer down.** D25 reads: *"Nothing the
UI renders may read a log — the audit view is the single exception, because it
is a literal tail."* The shipped boundary rule forbade `toolsurface/`, `web/`
and `cli/` from importing `shepherd.logs` at all, which is stricter than the
decision it implements, and M4 is the milestone that discovers it: `invoke()`
must **write** the audit log and `get_audit_log(limit=50)` must **read** it, and
both live at L4. The rejected repair — moving the writer and the reader down to
`orchestration/`, which `toolsurface/` may import freely — keeps the rule's
letter and defeats its purpose, and it is written down here, where the
temptation is. The permission this module holds is not an exemption list entry:
`tests/boundaries/test_l4_import_rules.py` discovers it **by property**, as the
module that defines `build_audit_sink`, so renaming this file moves the
permission with it and defining the factory without importing a log turns the
rule red.

**The sink never raises (E-M4-6), and this sentence is here so the next reader
does not "fix" it.** `RotatingJsonlLog` reports a failed write as `False` and
counts it in `lost`; the sink bumps `AUDIT_LINE_LOST` and returns. An exception
escaping the sink would kill a **destructive call mid-flight** — the tool has
already run — and a half-done `kill_session` is worse than a missing line. So
every failure the write can produce is counted, including one the log does not
promise, because "never raises" is the contract this module's caller depends on
and a contract proved only against a well-behaved log is a contract proved
against a fixture.

**The attribution claims exactly what the process knows (K23).** `approved_by`
carries whatever the gate decided — `claimed_human` when a caller stamped
`HUMAN` and policy allowed it, `user` only when a person pressed Approve on a
card. This module never translates between them. A record saying *a person
approved this* when nobody did is the artefact the next incident is
reconstructed from.

**It receives its log** (ADR-2, ADR-M2-6). It resolves no path, reads no
environment variable and asks no host: the composition root hands it
`RotatingJsonlLog(log_root(host), AUDIT_PREFIX)` and a test hands it `tmp_path`.
`build_audit_sink` has **no defaulted parameter**, so an audit sink that has no
log behind it is not a representable value — the same shape `install_chokepoint`
gives the gate one layer up (DP13), and for the same reason: revision 1's
`None`-defaulted sink made *no record* read as *nothing to record*.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.logs.jsonl import RotatingJsonlLog, scan_records
from shepherd.toolsurface.types import (
    REDACTED,
    SECRET_KEY_MARKERS,
    ActorKind,
    AuditRecord,
    AuditSink,
    CallerContext,
    actor_kind_of,
)

__all__ = [
    "AUDIT_PREFIX",
    "REDACTED",
    "SECRET_KEY_MARKERS",
    "UNKNOWN_DATE",
    "actor_kind_of",
    "build_audit_sink",
    "encode_audit_record",
    "read_audit_records",
    "redact_args",
]

#: The log's own subdirectory under the log root, so the stop log and the audit
#: log are siblings rather than an interleaving.
AUDIT_PREFIX = "audit"

#: Where a record whose `at` this build cannot read goes. Visible on `ls`,
#: because losing the line would be the worse failure — the same answer
#: `logs/stops.py` gives, and deliberately the same spelling.
UNKNOWN_DATE = "unknown-date"

#: §13's redaction rule and DP2's actor derivation are **imported, not declared**
#: (RD-T4-3 and §T6-4, closed in the QA-prep pass). Both were declared here and
#: copied — into `approvals.py` and into `registry.py` — because this module
#: imports `shepherd.logs.jsonl`, and importing *it* from either of those would
#: have dragged `shepherd.logs` into `shepherd status`. The shipped DP3 rule
#: checks only **direct** importers, so it would have passed while being
#: defeated. `types.py` is stdlib-only and is now the single home for all three
#: names; they stay in this module's `__all__` because `read_audit_records`'
#: callers read the redaction vocabulary off the module that redacts.


#: `at`, sliced. The one canonical stamp spelling is `core/clock.py`'s, and the
#: date is its first ten characters — this module never formats an instant.
_DATE_WIDTH = 10


def _is_secret_shaped(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def redact_args(args: Mapping[str, object]) -> Mapping[str, object]:
    """§13's rule, applied to the whole argument tree.

    **Not only the top level.** A tool whose schema declares an `object` or an
    `array` property can carry a nested `{"password": …}`, and a pass that
    stopped at depth one would write it out verbatim while every top-level
    assertion stayed green — which is why the test asserts on the encoded
    **bytes** rather than on the mapping.
    """
    return {
        key: REDACTED if _is_secret_shaped(key) else _redact_value(value)
        for key, value in args.items()
    }


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_args({str(key): item for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_redact_value(item) for item in value]
    return value


def encode_audit_record(record: AuditRecord) -> Mapping[str, object]:
    """One decided call → ADR-M4-1's JSON object, in the ADR's own key order.

    Field by field rather than `dataclasses.asdict`: a reflexive encoder changes
    the record silently whenever the dataclass changes, and the record is a
    90-day artefact that `jq` reads. `test_every_field_of_the_record_is_exercised`
    compares this key set to `fields(AuditRecord)` enumerated at test time, so a
    field added to the dataclass and not added here is a **failing build** and
    not a column that quietly stops appearing (K19).
    """
    return {
        "at": record.at,
        "correlation_id": record.correlation_id,
        "actor_kind": record.actor_kind.value,
        "actor_id": record.actor_id,
        "tool": record.tool,
        "blast_class": record.blast_class.value,
        "args": redact_args(record.args),
        "autonomy_level": record.autonomy_level,
        "decision": record.decision,
        "approved_by": record.approved_by,
        "approval_id": record.approval_id,
        "result": record.result,
        "failure": None if record.failure is None else record.failure.value,
        "duration_ms": record.duration_ms,
    }


def build_audit_sink(
    log: RotatingJsonlLog,
    bump: Callable[[AnomalyKind], None],
    date_of: Callable[[str], str | None],
) -> AuditSink:
    """The `AuditSink` the chokepoint is installed with (D8, DP13).

    Three injected things and **no defaults**, which is the property rather than
    a style: a sink with no log behind it cannot be constructed, so "the audit
    log was not on" is not a state this module can produce. `date_of` is
    injected for the same reason `log` is — it is the one reader of the stamp
    spelling, and a second speller here would be a second format.
    """

    def sink(record: AuditRecord) -> None:
        try:
            written = log.append(
                encode_audit_record(record), date_of(record.at) or UNKNOWN_DATE
            )
        except Exception:  # noqa: BLE001 - E-M4-6: the call has already run
            bump(AnomalyKind.AUDIT_LINE_LOST)
            return
        if not written:
            bump(AnomalyKind.AUDIT_LINE_LOST)

    return sink


def read_audit_records(root: Path, limit: int) -> tuple[Mapping[str, object], ...]:
    """D25's single UI exception: a literal tail, newest first.

    **The order is this reader's, not the file's.** Records are sorted on their
    own `at`, so a day-file written out of order — two writers, a clock stepping
    back, a rotation — still reads newest-first, and the ordering assertion in
    the test is not one the writer could have satisfied on its own.

    Malformed lines are skipped by `scan_records` (a daemon killed mid-write
    leaves one, which D25 requires a reader to survive), and a record whose `at`
    this build cannot read is skipped here: it cannot be placed in the order,
    and placing it anyway would be inventing a position.

    This is the **only** reader. `get_audit_log` projects what this returns;
    nothing else opens the directory, because D25's exception is a *view* and
    not a query surface.
    """
    if limit <= 0:
        return ()
    records, _stats = scan_records(root, AUDIT_PREFIX)
    datable = [record for record, _line in records if _at_of(record) is not None]
    datable.sort(key=lambda record: _at_of(record) or "", reverse=True)
    return tuple(datable[:limit])


def _at_of(record: Mapping[str, object]) -> str | None:
    at = record.get("at")
    return at if isinstance(at, str) and len(at) >= _DATE_WIDTH else None
