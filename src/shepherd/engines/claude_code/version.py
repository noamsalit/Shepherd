"""Engine identity: what version is running, and when drift was last checked.

Both facts are engine knowledge, so they live in the engine adapter (D19, D35) —
`cli/` may not run the engine binary and may not read a probe's output, and the
one layer §5.0 exists to keep free of the engine's vocabulary is exactly the one
that wants to print them.

Two rules, and both are principle 5:

* **A version we could not read is `None`**, never the pinned one. The pinned
  version is what `docs/specs/data-schemas.md` captured every shape at; printing
  it as the *running* version would turn "we did not look" into "they agree",
  which is the single most misleading thing this line could say.
* **A drift record we cannot read is `unchecked`**, never `clean`. The drift
  check (`docs/probes/drift_check.py`) is a gate: exit 1 on drift, 2 when it
  cannot check, 0 clean. A torn or absent record is the 2 case, and it reads as
  2 here rather than as a pass.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DRIFT_RECORD_NAME",
    "PINNED_ENGINE_VERSION",
    "DriftRecord",
    "engine_version",
    "read_drift_record",
]

#: The engine version every capture in `docs/specs/data-schemas.md` is pinned to
#: (its header: `claude --version` = `2.1.270 (Claude Code)` on 2026-09-14).
PINNED_ENGINE_VERSION = "2.1.270"

#: Where `drift_check.py --record <data_dir>` writes its verdict. The file lives
#: beside the database because it is a fact about *this host's* engine.
DRIFT_RECORD_NAME = "engine-drift-check.json"

#: The three verdicts, matching the probe's three exit statuses.
VERDICT_CLEAN = "clean"
VERDICT_DRIFT = "drift"
VERDICT_UNCHECKED = "unchecked"

_VERDICTS = frozenset({VERDICT_CLEAN, VERDICT_DRIFT, VERDICT_UNCHECKED})

_VERSION_PATTERN = re.compile(r"(\d+\.\d+\.\d+)")

#: A version read is a courtesy line on `doctor`, not a dependency: it is bounded
#: so a wedged binary costs a second, not the command.
VERSION_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class DriftRecord:
    """One recorded run of the drift gate on this host."""

    checked_at: str
    engine_version: str | None
    pinned_version: str
    verdict: str
    detail: str


def engine_version(timeout_s: float = VERSION_TIMEOUT_S) -> str | None:
    """`claude --version`, or `None` when there is no answer to be had.

    Never `shell=True`, and never an exception: an engine that is not installed
    is a fact `doctor` prints, not a command that fails.
    """
    try:
        completed = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    found = _VERSION_PATTERN.search(completed.stdout)
    return found.group(1) if found else None


def read_drift_record(path: Path) -> DriftRecord | None:
    """The recorded verdict, or `None` — which reads as *unchecked*, not clean."""
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    verdict = decoded.get("verdict")
    checked_at = decoded.get("checked_at")
    if not isinstance(verdict, str) or verdict not in _VERDICTS:
        return None
    if not isinstance(checked_at, str) or checked_at == "":
        return None
    version = decoded.get("engine_version")
    pinned = decoded.get("pinned_version")
    detail = decoded.get("detail")
    return DriftRecord(
        checked_at=checked_at,
        engine_version=version if isinstance(version, str) else None,
        pinned_version=pinned if isinstance(pinned, str) else PINNED_ENGINE_VERSION,
        verdict=verdict,
        detail=detail if isinstance(detail, str) else "",
    )
