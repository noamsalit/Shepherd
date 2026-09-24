"""The audit sink, read off disk — the production one, not a fixture's list.

Copied from `tests/qa5/auditprobe.py` (re-proved by
`fixtures/mutations/auditprobe.json`, env-plan §4 step 1a). The one change: the
root is resolved from an instance's sandboxed `MacHost(environ)` through the
product's own `compose.log_root(host)` and `audit.AUDIT_PREFIX` — never spelled
— so a product that moved either would leave this reading an empty directory
and the count assertions would fail rather than pass vacuously.

Records are JSON objects, asserted by key and value, never by substring
(test-plan §5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from shepherd.host.mac import MacHost
from shepherd.logs.jsonl import scan_records
from shepherd.toolsurface.audit import AUDIT_PREFIX
from shepherd.toolsurface.compose import log_root

from .sandbox import InstanceRoot
from .verdict import Blocked

#: The verbs that change something. Reads are gated invokes too and append a
#: `local_read` row each, so counting is done over mutations wherever the
#: browser or the harness may read in between (qa5's measured lesson).
MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "create_project",
        "rename_project",
        "set_project_description",
        "delete_project",
        "add_repo",
        "remove_repo",
        "set_autonomy_level",
        "rename_session",
        "decide_approval",
    }
)

#: The fields test-plan §5 names on every record (audit.py key order).
REQUIRED_FIELDS: tuple[str, ...] = (
    "at", "correlation_id", "actor_kind", "actor_id", "tool", "blast_class", "args",
    "autonomy_level", "decision", "approved_by", "approval_id", "result", "failure", "duration_ms",
)


@dataclass(frozen=True)
class AuditProbe:
    root: Path

    @classmethod
    def for_instance(cls, instance: InstanceRoot) -> AuditProbe:
        host = MacHost(environ={"HOME": str(instance.home), "TMPDIR": str(instance.tmpdir)})
        return cls(root=log_root(host) / AUDIT_PREFIX)

    def records(self, *, absent_ok: bool = False) -> list[Mapping[str, object]]:
        """Every audit record. An absent log dir is `[]` only for a `mark()` taken before the
        first request (`absent_ok`); anywhere else it is `Blocked` — every GET is audited, so a
        missing dir means the harness is reading the wrong path, and a "no row" clause over it
        would be vacuous (hunter M8)."""
        if not self.root.parent.exists():
            if absent_ok:
                return []
            raise Blocked(f"the audit log dir {self.root.parent} does not exist: the harness cannot read "
                          "the product's audit (a path mismatch), so no audit clause can be evaluated")
        found, stats = scan_records(self.root.parent, AUDIT_PREFIX)
        assert stats.skipped_malformed == 0, f"malformed audit records: {stats}"
        assert stats.unreadable_files == 0, f"unreadable audit files: {stats}"
        return [record for record, _line in found]

    def mark(self) -> int:
        return len(self.records(absent_ok=True))

    def since(self, mark: int) -> list[Mapping[str, object]]:
        return self.records()[mark:]

    def tools_since(self, mark: int) -> list[str]:
        return [str(record.get("tool")) for record in self.since(mark)]

    def mutations_since(self, mark: int) -> list[Mapping[str, object]]:
        return [row for row in self.since(mark) if row.get("tool") in MUTATION_TOOLS]

    def records_for(self, mark: int, tool: str) -> list[Mapping[str, object]]:
        return [row for row in self.since(mark) if row.get("tool") == tool]

    def by_correlation(self, mark: int, correlation_id: str) -> list[Mapping[str, object]]:
        return [row for row in self.since(mark) if row.get("correlation_id") == correlation_id]


def shape_problems(records: Sequence[Mapping[str, object]]) -> list[str]:
    """Every named key present, on every record. Never a formatted substring."""
    problems: list[str] = []
    for record in records:
        missing = [name for name in REQUIRED_FIELDS if name not in record]
        if missing:
            problems.append(f"record {record.get('tool')!r} missing {missing}")
        if not isinstance(record.get("args"), dict):
            problems.append(f"record {record.get('tool')!r} args is not a mapping")
    return problems
