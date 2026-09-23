"""Scenario records, and the report emitter whose publish gate can say FAIL.

The fix for round 5's O1/O14 (existing-harness §2): qa5 published
`qa5-latest.json` regardless of pytest's exit status or a teardown problem, and
run 2 overwrote run 1's red. Here:

* one record per scenario, `{id, wave, tier, class, lane, verdict: PASS|FAIL|
  BLOCKED, fail_kind: assert|bound|null, predicted, oracle_source, clauses[],
  evidence[]}` (env-plan §10);
* **GREEN** only if every lane's pytest exit status is 0, the teardown problem
  list is empty, there is exactly one record per planned id (161), and there is
  no FAIL and no BLOCKED;
* **RED** if any FAIL (any incompleteness is listed beside it, never hidden);
* **INCOMPLETE** otherwise: a missing or duplicate record, a crashed lane (exit
  not 0/1, or exit 1 with no FAIL/BLOCKED record from that lane), a teardown
  problem, or any BLOCKED;
* every run writes an **immutable** `runs/<run_id>.json` (refused if it exists)
  and `runs/<run_id>/report.md`; `qa6-latest.json` is a copy carrying its own
  status and the list of every run so far, so a later green cannot hide an
  earlier red.

`decide_status` is pure so the guard tests can drive it with synthetic inputs.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .catalog import BY_ID, PLANNED_TOTAL, SCENARIOS

RECORDS_DIR = "records"
LATEST = "qa6-latest.json"
HISTORY = "qa6-history.jsonl"


def record_path(run_dir: Path, lane: str, wave: str) -> Path:
    return run_dir / RECORDS_DIR / f"{lane}-w{wave}.jsonl"


def build_record(
    scenario_id: str,
    *,
    verdict: str,
    fail_kind: str | None,
    reason: str,
    clauses: Sequence[Mapping[str, str]],
    evidence: Sequence[str],
    node: str,
    lane_process: str,
    duration_s: float,
) -> dict[str, object]:
    meta = BY_ID.get(scenario_id)
    return {
        "id": scenario_id,
        "wave": meta.wave if meta else None,
        "tier": meta.tier if meta else None,
        "class": meta.klass if meta else None,
        "lane": meta.lane if meta else None,
        "predicted": meta.predicted if meta else None,
        "oracle_source": meta.oracle_source if meta else None,
        "verdict": verdict,
        "fail_kind": fail_kind,
        "reason": reason,
        "clauses": [dict(clause) for clause in clauses],
        "evidence": list(evidence),
        "node": node,
        "lane_process": lane_process,
        "duration_s": round(duration_s, 3),
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def append_record(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")


def load_records(run_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    directory = run_dir / RECORDS_DIR
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decoded: object = json.loads(line)
                if isinstance(decoded, dict):
                    records.append({str(key): value for key, value in decoded.items()})
    return records


@dataclass(frozen=True)
class LaneExit:
    lane: str
    wave: str
    exit_code: int
    command: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    status: str
    reasons: tuple[str, ...]
    counts: dict[str, int]


def decide_status(
    records: Sequence[Mapping[str, object]],
    lane_exits: Sequence[LaneExit],
    teardown_problems: Sequence[str],
    planned_ids: Iterable[str],
) -> Decision:
    """The publish gate. Pure."""
    planned = list(planned_ids)
    reasons: list[str] = []
    ids = [str(record.get("id")) for record in records]
    counts = Counter(str(record.get("verdict")) for record in records)
    duplicates = sorted(sid for sid, n in Counter(ids).items() if n > 1)
    missing = sorted(set(planned) - set(ids))
    unplanned = sorted(set(ids) - set(planned))
    if duplicates:
        reasons.append(f"duplicate records: {duplicates}")
    if missing:
        reasons.append(f"{len(missing)} planned scenario(s) have no record: {missing[:40]}{'…' if len(missing) > 40 else ''}")
    if unplanned:
        reasons.append(f"records for ids not in the plan: {unplanned}")
    if len(records) != len(planned):
        reasons.append(f"record count {len(records)} != planned {len(planned)}")
    lanes_with_verdicts: dict[str, set[str]] = {}
    for record in records:
        lane = str(record.get("lane_process"))
        lanes_with_verdicts.setdefault(lane, set()).add(str(record.get("verdict")))
    for lane_exit in lane_exits:
        key = f"{lane_exit.lane}-w{lane_exit.wave}"
        verdicts = lanes_with_verdicts.get(key, set())
        if lane_exit.exit_code == 0:
            continue
        if lane_exit.exit_code == 1 and verdicts & {"FAIL", "BLOCKED"}:
            reasons.append(f"lane {key} exited 1 (it recorded FAIL/BLOCKED)")
            continue
        reasons.append(f"lane {key} crashed: exit {lane_exit.exit_code} with verdicts {sorted(verdicts)}")
    if teardown_problems:
        reasons.append(f"{len(teardown_problems)} teardown problem(s): {list(teardown_problems)[:10]}")
    if counts.get("BLOCKED", 0):
        reasons.append(f"{counts['BLOCKED']} BLOCKED scenario(s)")
    if counts.get("FAIL", 0):
        return Decision("RED", (f"{counts['FAIL']} FAIL scenario(s)", *reasons), dict(counts))
    clean = (
        not reasons
        and all(lane.exit_code == 0 for lane in lane_exits)
        and len(records) == len(planned)
        and counts.get("PASS", 0) == len(planned)
    )
    if clean:
        return Decision("GREEN", ("every planned scenario PASS, every lane exit 0, clean teardown",), dict(counts))
    return Decision("INCOMPLETE", tuple(reasons) or ("not every planned scenario passed",), dict(counts))


def write_report(
    report_dir: Path,
    run_id: str,
    run_dir: Path,
    lane_exits: Sequence[LaneExit],
    teardown_problems: Sequence[str],
    extra: Mapping[str, object] | None = None,
) -> Decision:
    """Write the immutable run file, the markdown, and the latest copy."""
    records = load_records(run_dir)
    decision = decide_status(records, lane_exits, teardown_problems, [s.id for s in SCENARIOS])
    run_file = report_dir / f"{run_id}.json"
    if run_file.exists():
        raise FileExistsError(f"{run_file} exists; a run's report is immutable")
    payload: dict[str, object] = {
        "run_id": run_id,
        "status": decision.status,
        "reasons": list(decision.reasons),
        "counts": decision.counts,
        "planned": PLANNED_TOTAL,
        "lane_exits": [
            {"lane": lane.lane, "wave": lane.wave, "exit_code": lane.exit_code, "command": list(lane.command)}
            for lane in lane_exits
        ],
        "teardown_problems": list(teardown_problems),
        "records": sorted(records, key=lambda record: _order(str(record.get("id")))),
        **(dict(extra) if extra else {}),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    run_file.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    run_file.chmod(0o444)
    (run_dir / "report.md").write_text(render_markdown(payload), encoding="utf-8")
    history_line = {"run_id": run_id, "status": decision.status, "counts": decision.counts,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(report_dir / HISTORY, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_line, sort_keys=True) + "\n")
    history = [json.loads(line) for line in (report_dir / HISTORY).read_text(encoding="utf-8").splitlines() if line]
    latest = dict(payload)
    latest["history"] = history
    latest_path = report_dir / LATEST
    if latest_path.exists():
        latest_path.chmod(0o644)
    latest_path.write_text(json.dumps(latest, indent=1, sort_keys=True), encoding="utf-8")
    return decision


def _order(scenario_id: str) -> tuple[int, int]:
    ids = [s.id for s in SCENARIOS]
    meta = BY_ID.get(scenario_id)
    return (meta.wave if meta else 99, ids.index(scenario_id) if scenario_id in ids else 999)


def render_markdown(payload: Mapping[str, object]) -> str:
    lines = [
        f"# qa6 run {payload.get('run_id')}",
        "",
        f"**Status: {payload.get('status')}**",
        "",
    ]
    reasons = payload.get("reasons")
    if isinstance(reasons, list):
        lines += [f"- {reason}" for reason in reasons]
    lines += ["", f"Counts: {payload.get('counts')}", "", "| id | wave | verdict | kind | predicted | reason |", "|---|---|---|---|---|---|"]
    records = payload.get("records")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            reason = str(record.get("reason") or "").replace("|", "\\|").replace("\n", " ")[:300]
            predicted = str(record.get("predicted") or "").replace("|", "\\|")[:80]
            lines.append(
                f"| {record.get('id')} | {record.get('wave')} | {record.get('verdict')} | "
                f"{record.get('fail_kind') or ''} | {predicted} | {reason} |"
            )
    lines += ["", "## Teardown problems", ""]
    problems = payload.get("teardown_problems")
    if isinstance(problems, list) and problems:
        lines += [f"- {problem}" for problem in problems]
    else:
        lines.append("none")
    return "\n".join(lines) + "\n"
