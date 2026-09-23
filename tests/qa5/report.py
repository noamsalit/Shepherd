"""The run report emitter — the shape `qa-executor` must produce.

Scenarios append **evidence**, not prose: an id, a verdict, the expected and the
actual, and the bindings a later scenario consumes. Three rules this module
makes structural:

* **`BLOCKED` is a distinct outcome from `FAIL` and from `PASS`.** A scenario
  that could not run has not passed, and it never rounds up.
* **Every loss is stated, never absorbed.** A suite that quietly drops 60% of
  its scenarios and reports PASS is worse than one that fails, because it
  manufactures confidence.
* **Declarations are carried verbatim.** S30's AC-28 sentence must appear in the
  report exactly as the plan writes it, because a PASS on the substitute does
  not discharge the criterion it substitutes for.

* **`qa5-latest.json` is PUBLISHED, not written.** `emit()` writes the run file
  unconditionally — that file is evidence and a partial run is still evidence —
  but only `publish_latest()` makes a run *the* run, and `conftest` calls it
  only when the record set is exactly the planned one. Measured before this
  split: 140 run files, `FAIL` total 0, and 47 of them all-green with
  `scenarios: 0`, each of which had overwritten `latest`. A report that cannot
  express a failure manufactures the confidence it was built to check.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFLOW = "wf-20260921T212808Z-9172ed6b"
REPORT_DIR = Path("/root/Shepherd/.cc10x/qa") / WORKFLOW / "runs"

#: S30 carries this verbatim. It is a constant so no run can paraphrase it into
#: something that reads like a discharge.
AC28_DECLARATION = (
    "AC-28's final clause was **not run**. Its command invokes `pytest -m live`, "
    "which starts real `claude` processes against the user's real `~/.claude.json` "
    "and is forbidden by a standing user constraint. S30 is a substitute sweep "
    "carrying no `live` marker, and a PASS here does not discharge AC-28."
)


#: A **product defect this harness reproduced and then settled around.** It is a
#: constant for the same reason `AC28_DECLARATION` is: a finding that exists only
#: as a Python comment in a test file has not been reported to anyone. "Every loss
#: is stated, never absorbed" applies to a loss the harness worked around just as
#: much as to one it could not.
LOAD_DETAIL_RACE_DECLARATION = (
    "PRODUCT DEFECT, reproduced and worked around, not fixed: "
    "`web/static/projects.js:252-256` — `projectRow`'s click handler calls "
    "`loadDetail(project.project_id)` WITHOUT awaiting it and then `renderList()`, "
    "while `submitProject`'s create branch already has a `loadDetail` of its own in "
    "flight. Two unawaited reads race and the later one to RESOLVE wins, so the "
    "detail pane can show a project for a frame and then be overwritten — leaving "
    "`#proj-edit` bound to a different project and the draft path list stuck at "
    "zero. Measured at approximately one full-suite run in four. A real user hits "
    "it by clicking a project row while a create is still settling. The harness "
    "settles on `networkidle` before reading the pane, which is sound on this page "
    "specifically (the product runs no timers: zero setInterval / setTimeout / "
    "requestAnimationFrame across its JS, so 'no requests in flight' is a stable "
    "state rather than a gap between ticks) — but a settle in the test does not "
    "fix the product, and the defect is shipped."
)


@dataclass
class Evidence:
    scenario: str
    tier: str
    verdict: str
    expected: str
    actual: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunReport:
    started_at: str = ""
    finished_at: str = ""
    revision: str = "r5-remfix1"
    scenarios: list[Evidence] = field(default_factory=list)
    bindings: dict[str, Any] = field(default_factory=dict)
    declarations: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)
    teardown: list[str] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)

    def record(
        self,
        scenario: str,
        tier: str,
        verdict: str,
        expected: str,
        actual: str,
        **detail: Any,
    ) -> None:
        if verdict not in {"PASS", "FAIL", "BLOCKED", "PARTIAL"}:
            raise ValueError(f"{verdict!r} is not one of PASS/FAIL/BLOCKED/PARTIAL")
        self.scenarios.append(
            Evidence(
                scenario=scenario,
                tier=tier,
                verdict=verdict,
                expected=expected,
                actual=actual,
                detail=detail,
            )
        )

    def bind(self, name: str, value: Any) -> None:
        """S0's four lists, recorded verbatim so a reader can check them."""
        self.bindings[name] = value

    def declare(self, text: str) -> None:
        if text not in self.declarations:
            self.declarations.append(text)

    def lose(self, text: str) -> None:
        if text not in self.losses:
            self.losses.append(text)

    def measure(self, name: str, value: Any) -> None:
        self.measurements[name] = value

    # ----- emission ---------------------------------------------------------
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "PARTIAL": 0}
        for evidence in self.scenarios:
            tally[evidence.verdict] += 1
        return tally

    def emit(self, directory: Path | None = None) -> Path:
        target = directory or REPORT_DIR
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = target / f"qa5-run-{stamp}-{os.getpid()}.json"
        path.write_text(
            json.dumps(
                {
                    "workflow": WORKFLOW,
                    "revision": self.revision,
                    "started_at": self.started_at,
                    "finished_at": self.finished_at,
                    "counts": self.counts(),
                    "scenarios": [asdict(item) for item in self.scenarios],
                    "bindings": self.bindings,
                    "declarations": self.declarations,
                    "losses": self.losses,
                    "teardown": self.teardown,
                    "measurements": self.measurements,
                },
                indent=2,
                sort_keys=False,
                default=str,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def publish_latest(run_file: Path) -> Path:
        """Make `run_file` the published `qa5-latest.json`.

        Separate from `emit` **on purpose**: publication is a claim that the run
        accounted for every planned scenario, and the caller that can check that
        is the session hook, not the emitter.
        """
        latest = run_file.parent / "qa5-latest.json"
        latest.write_text(run_file.read_text(encoding="utf-8"), encoding="utf-8")
        return latest
