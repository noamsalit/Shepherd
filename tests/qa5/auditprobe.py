"""The audit sink, read off disk — the production one, not a fixture's list.

PP-6's whole point is that the prior claim *"two autonomy POSTs append two audit
rows"* was **reasoned, not measured**: the chokepoint fixture every earlier test
used collects into a Python list and never touches disk. This module reads the
real `RotatingJsonlLog` under `$XDG_DATA_HOME/shepherd/logs/<AUDIT_PREFIX>/`.

Two things are resolved rather than spelled: the **prefix** comes from
`shepherd.toolsurface.audit`, and the **root** from `compose.log_root(host)`. A
harness that spelled `"audit"` and `"logs"` would keep passing after the product
moved either, and would then be measuring an empty directory.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from shepherd.host.base import HostPlatform
from shepherd.logs.jsonl import scan_records
from shepherd.toolsurface.audit import AUDIT_PREFIX
from shepherd.toolsurface.compose import log_root

#: **Every gated invoke appends a record, and reads are gated invokes.**
#: `list_projects`, `get_project` and `fleet_summary` all append, so a scenario
#: that asserted the *whole* tail equalled its own calls would be asserting that
#: nothing read the page — which the browser does constantly, and which the
#: harness itself does to check a precondition. Counting is therefore done over
#: the **mutations**, named here once. A tool missing from this set is counted
#: by nobody, so it is a closed set of the verbs this plan drives and not a
#: "things to ignore" list.
MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "create_project",
        "rename_project",
        "set_project_description",
        "delete_project",
        "add_repo",
        "remove_repo",
        "set_autonomy_level",
    }
)

#: The fields §5 quotes as required on every record. The record's *serialised
#: format* is not quoted, so nothing here asserts key order or whitespace.
REQUIRED_FIELDS: tuple[str, ...] = ("at", "tool", "decision", "approved_by")


@dataclass(frozen=True)
class AuditProbe:
    """Everything a scenario needs to count records between two marks."""

    root: Path

    @classmethod
    def for_host(cls, host: HostPlatform) -> AuditProbe:
        return cls(root=log_root(host) / AUDIT_PREFIX)

    def records(self) -> list[Mapping[str, object]]:
        found, stats = scan_records(self.root.parent, AUDIT_PREFIX)
        assert stats.skipped_malformed == 0, f"malformed audit records: {stats}"
        assert stats.unreadable_files == 0, f"unreadable audit files: {stats}"
        return [record for record, _line in found]

    def mark(self) -> int:
        """The record count right now — one end of a counted span."""
        return len(self.records())

    def since(self, mark: int) -> list[Mapping[str, object]]:
        return self.records()[mark:]

    def tools_since(self, mark: int) -> list[str]:
        return [str(record.get("tool")) for record in self.since(mark)]

    def mutations_since(self, mark: int) -> list[Mapping[str, object]]:
        """Only the verbs that change something — reads are gated too."""
        return [row for row in self.since(mark) if row.get("tool") in MUTATION_TOOLS]

    def mutation_tools_since(self, mark: int) -> list[str]:
        return [str(row.get("tool")) for row in self.mutations_since(mark)]

    def records_for(self, mark: int, tool: str) -> list[Mapping[str, object]]:
        return [row for row in self.since(mark) if row.get("tool") == tool]


def assert_shape(records: Sequence[Mapping[str, object]]) -> None:
    """Every named key present, on every record. Never a formatted substring."""
    for record in records:
        for field_name in REQUIRED_FIELDS:
            assert field_name in record, f"audit record missing {field_name!r}: {record!r}"
        assert isinstance(record.get("args"), dict), f"args is not a mapping: {record!r}"
        assert isinstance(record.get("at"), str) and record["at"], record
