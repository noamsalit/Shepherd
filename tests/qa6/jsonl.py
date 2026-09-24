"""One reader for the harness's append-only JSONL files that survives a torn line.

Hunter N1 / N5, review N4: a lane process SIGTERM'd at its timeout (or a disk
that filled mid-append) can leave a half-written last line in a record,
problem or pid ledger file. Every reader used to call `json.loads(line)` bare,
so one torn line made the finalizer publish nothing and the teardown orphan
every child. Here a line that does not parse as a JSON object is **returned as
a problem** beside the rows that did parse: it is never raised, and never
dropped silently. The caller decides where the problem is published (the run's
harness problems, a teardown problem).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JsonlRead:
    rows: list[dict[str, object]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def read_objects(path: Path) -> JsonlRead:
    """Every JSON-object line of `path` (absent = empty), and one problem per line that is not one."""
    result = JsonlRead()
    if not path.exists():
        return result
    text = path.read_bytes().decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            decoded: object = json.loads(line)
        except json.JSONDecodeError as error:
            result.problems.append(f"{path}: line {number} is not JSON (a torn write?): {error}: {line[:200]!r}")
            continue
        if not isinstance(decoded, dict):
            result.problems.append(f"{path}: line {number} is not a JSON object: {line[:200]!r}")
            continue
        result.rows.append({str(key): value for key, value in decoded.items()})
    return result
