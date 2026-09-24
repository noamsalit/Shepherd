"""Mutation proofs: every assertion the floor names must be seen to go false.

Two kinds, both driven from outside the code they sabotage:

1. **Scenario mutations** (the §2c floor: one per `At risk of appearing proven:
   yes` property STAGE A's waves cover — PP-10, PP-14, PP-15). A scenario reads
   `active(<name>)` at exactly one input it controls and, when the runner sets
   `QA6_MUTATION=<name>`, feeds the product a *different* input and notes
   `QA6 MUTATION <name> APPLIED: …` in its evidence. The named clause must then
   evaluate false. The product is never edited (PRODUCT_CODE_TOUCHED stays
   false); what is sabotaged is the correspondence between the fixture and
   the oracle, which is exactly what "the assertion can fail" means here.
2. **Module mutations** of the five helpers copied from `tests/qa5` (env-plan
   §4 step 1a). The patch is an inert JSON fixture under
   `fixtures/mutations/<module>.json` ({"file", "old", "new", "proof",
   "expect"}), read as text and never imported. The driver copies the package
   to a temp dir, applies the patch there, and runs the named proof test in a
   fresh subprocess with `PYTHONDONTWRITEBYTECODE=1` against the copy (so no
   stale `.pyc` can hide it — CLAUDE.md mutation rule 4). Every patched line is
   pure: none sends a signal, starts a process, binds a port or runs tmux
   (CLAUDE.md rules 1-3); the tmuxctl mutation is proved by predicate, never by
   execution.

`run_scenario_mutation` is the runner's `--mutation NAME`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths

ENV = "QA6_MUTATION"
FIXTURES = paths.QA6_DIR / "fixtures" / "mutations"


def active(name: str) -> bool:
    """True only when the runner is proving this exact mutation."""
    return os.environ.get(ENV) == name


@dataclass(frozen=True)
class ScenarioMutation:
    name: str
    prop: str
    scenario: str
    node: str
    failing_clause: str
    what: str


_STAGE_A: tuple[ScenarioMutation, ...] = (
        ScenarioMutation("PP14-D1-status", "PP-14", "D1",
                         "tests/qa6/sub/test_wave3_1_discovery.py::test_d1_busy_sidecar_registers_running_attached",
                         "db.running",
                         "D1's sidecar says status 'waiting' instead of 'busy'; the running-state clause must go false"),
        ScenarioMutation("PP15-D12-frame", "PP-15", "D12",
                         "tests/qa6/sub/test_wave3_3_hooks.py::test_d12_mechanical_stop_evidence_maps_to_spec_reason_and_bucket",
                         "verdict.rate_limit.stop_reason",
                         "the rate_limit case's StopFailure carries error 'server_error'; its stop_reason clause must go false"),
        ScenarioMutation("PP10-E3-lastid", "PP-10", "E3",
                         "tests/qa6/sub/test_wave2_4_sse.py::test_e3_last_event_id_resumes_exactly_within_the_ring",
                         "stream.first_five_are_k_plus_1_to_5",
                         "the resume sends Last-Event-ID k+1 instead of k (an off-by-one); the exact-resume clause must go false"),
)


def _registered() -> dict[str, ScenarioMutation]:
    """STAGE A's entries plus one inert JSON file per later mutation.

    A later wave registers a scenario mutation by **adding**
    `fixtures/mutations/scenarios/<name>.json` with the six fields below — a
    new file, never an edit to this module.
    """
    found = {m.name: m for m in _STAGE_A}
    directory = FIXTURES / "scenarios"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict):
            raise AssertionError(f"{path} is not an object")
        entry = ScenarioMutation(**{key: str(decoded[key]) for key in
                                    ("name", "prop", "scenario", "node", "failing_clause", "what")})
        if entry.name in found:
            raise AssertionError(f"scenario mutation {entry.name} is registered twice")
        found[entry.name] = entry
    return found


SCENARIO_MUTATIONS: dict[str, ScenarioMutation] = _registered()


S0_NODE = "tests/qa6/live/test_wave1_s0_auth_probe.py::test_s0_bind_live_auth_mode"
LIVE_WAVE = 8


def run_scenario_mutation(name: str, report_dir: Path) -> int:
    """Mint a run, run the one node with the mutation live, and record the outcome.

    A wave-8 node needs the `LIVE_AUTH_MODE` S0 binds in the same run (SI-3):
    S0 runs first, in its own pytest process **without** the mutation, and the
    mode it wrote to `<run_dir>/live_auth_mode.json` is handed to the mutated
    node's process as `QA6_LIVE_AUTH_MODE` — exactly what the runner does.
    """
    from . import bootstrap, realclaude, teardown
    from .report import load_records
    from .sandbox import ENV_LIVE_AUTH_MODE, pytest_process_env

    mutation = SCENARIO_MUTATIONS[name]
    run_id = time.strftime(f"qa6-mutation-{name}-%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = report_dir / "mutations" / run_id
    run = bootstrap.mint(os.getpid(), run_id, run_dir)
    knobs = {"QA6_RUN_PID": str(run.pid), "QA6_RUN_ID": run_id, "QA6_RUN_DIR": str(run_dir), "QA6_LANE": "mutation",
             "QA6_WAVE": "m"}
    base = [str(paths.PYTEST), "-p", "no:randomly", "-p", "no:cacheprovider", "-m", "qa6 or qa6live", "-q"]
    argv = [*base, mutation.node]
    prerequisite: dict[str, object] = {}
    try:
        for node in prerequisite_nodes(mutation):
            pre_argv = [*base, node]
            pre = subprocess.run(pre_argv, env=pytest_process_env(os.environ, {**knobs, "QA6_LANE": "mutation-prereq",
                                                                              "QA6_WAVE": "1"}),
                                 cwd=str(paths.REPO), capture_output=True, text=True, timeout=900, check=False)
            prerequisite[node] = {"command": " ".join(pre_argv), "exit": pre.returncode, "stdout_tail": pre.stdout[-800:]}
        mode = bound_live_auth_mode(run_dir) if prerequisite else None
        if mode is not None:
            knobs[ENV_LIVE_AUTH_MODE] = mode
        prerequisite["live_auth_mode"] = mode
        done = subprocess.run(argv, env=pytest_process_env(os.environ, {**knobs, ENV: name}), cwd=str(paths.REPO),
                              capture_output=True, text=True, timeout=1800, check=False)
    finally:
        bootstrap.remove_worktree(run)
        teardown.teardown_run(run)
    records = [r for r in load_records(run_dir) if r.get("id") == mutation.scenario]
    record = records[-1] if records else {}
    raw_clauses = record.get("clauses")
    clauses: list[object] = list(raw_clauses) if isinstance(raw_clauses, list) else []
    falsified = [c for c in clauses if isinstance(c, dict) and c.get("name") == mutation.failing_clause
                 and c.get("result") == "fail"]
    raw_evidence = record.get("evidence")
    evidence = [e for e in (raw_evidence if isinstance(raw_evidence, list) else [])
                if isinstance(e, str) and e.startswith(f"QA6 MUTATION {name}")]
    outcome = "assertion_falsified" if falsified and evidence else ("survived" if evidence else "blocked")
    link_changed = realclaude.link_change(run_dir)
    result = {
        "name": name, "property": mutation.prop, "scenario": mutation.scenario, "targets": f"{mutation.scenario} {mutation.failing_clause}",
        "what": mutation.what, "command": " ".join(argv), "env": f"{ENV}={name}", "exit": done.returncode,
        "prerequisite": prerequisite, "applied_evidence": evidence, "failing_assertion": mutation.failing_clause,
        "falsified_clause": falsified, "verdict": record.get("verdict"), "reason": record.get("reason"),
        "outcome": outcome, "claude_link_changed": link_changed, "stdout_tail": done.stdout[-2000:],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "mutation-result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    return 0 if outcome == "assertion_falsified" and link_changed is None else 1


def prerequisite_nodes(mutation: ScenarioMutation) -> list[str]:
    """Nodes run first, each in its own process, without the mutation: S0 for a wave-8 scenario."""
    from .catalog import BY_ID

    return [S0_NODE] if BY_ID[mutation.scenario].wave == LIVE_WAVE else []


def bound_live_auth_mode(run_dir: Path) -> str | None:
    """The `LIVE_AUTH_MODE` S0 wrote for this run, if it wrote one."""
    source = run_dir / "live_auth_mode.json"
    if not source.exists():
        return None
    decoded: object = json.loads(source.read_text(encoding="utf-8"))
    mode = decoded.get("LIVE_AUTH_MODE") if isinstance(decoded, dict) else None
    return mode if isinstance(mode, str) else None


# ----- module mutations (the copied qa5 helpers) --------------------------------------


@dataclass(frozen=True)
class ModuleMutation:
    module: str
    file: str
    old: str
    new: str
    proof: str
    expect: str


def load_module_mutation(module: str) -> ModuleMutation:
    decoded: object = json.loads((FIXTURES / f"{module}.json").read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError(f"{module}.json is not an object")
    fields = {key: str(decoded[key]) for key in ("file", "old", "new", "proof", "expect")}
    return ModuleMutation(module=module, **fields)


def run_module_mutation(mutation: ModuleMutation, *, mutated: bool) -> tuple[int, str, list[str]]:
    """Run the proof against a temp copy of the package (patched when `mutated`)."""
    with tempfile.TemporaryDirectory(prefix="qa6mut-", dir="/tmp") as scratch:
        base = Path(scratch)
        shutil.copytree(paths.QA6_DIR, base / "qa6", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        target = base / "qa6" / mutation.file
        text = target.read_text(encoding="utf-8")
        if mutated:
            if text.count(mutation.old) != 1:
                return -1, f"the mutation's 'old' text occurs {text.count(mutation.old)} times in {mutation.file}", []
            target.write_text(text.replace(mutation.old, mutation.new), encoding="utf-8")
        leftovers = [str(p) for p in base.rglob("__pycache__")]
        env = {key: value for key, value in os.environ.items() if not key.startswith("QA6_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=f"{base}:{paths.REPO / 'src'}")
        argv = [str(paths.PYTEST), "-p", "no:randomly", "-p", "no:cacheprovider", "-q", "-o", "addopts=",
                "--rootdir", str(base), "-c", os.devnull, "-m", "qa6", f"{base}/qa6/test_harness_guards.py::{mutation.proof}"]
        done = subprocess.run(argv, env=env, cwd=str(base), capture_output=True, text=True, timeout=300, check=False)
        return done.returncode, (done.stdout + done.stderr)[-3000:], leftovers
