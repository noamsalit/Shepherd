"""Mutation driver for the QA round 5 harness.

**It mutates ASSERTIONS in test files, never product code and never a
component.** Killing a component and watching a scenario stop proves dependency,
not discrimination; the floor is *this named check evaluated false*.

Every planted value is inert data — an expected string, a number, a comparison.
Nothing planted here is a signal, a kill, a reboot-capable call or a teardown
verb, in the repo or anywhere else.

`__pycache__` is cleared before every run: CPython decides a `.pyc` is fresh from
`(source mtime in whole seconds, source size)`, so a size-preserving mutation
landing within the same second as the last compile re-imports the UNMUTATED
bytecode and records a false survivor.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/root/Shepherd")
PY_BIN = REPO / ".venv/bin/python"

MUTATIONS = [
    {
        "pp": "PP-1",
        "signature": 'kinds == list(SIX)[:5]',
        "property": "Every succeeded project mutation reaches a second live client as one project.* frame",
        "file": "tests/qa5/test_wave2_events.py",
        "test": "tests/qa5/test_wave2_events.py::test_s4_all_six_mutations_reach_a_second_client",
        "old": "    assert kinds == list(SIX), kinds",
        "new": "    assert kinds == list(SIX)[:5], kinds  # MUTANT",
        "failing_assertion": "S4: kinds == list(SIX) — the six project.* frame kinds at client B, in order",
    },
    {
        "pp": "PP-2",
        "signature": 'window.assert_kinds(["project.renamed"])',
        "property": "A refused mutation reaches no client at all",
        "file": "tests/qa5/test_wave2_events.py",
        "test": "tests/qa5/test_wave2_events.py::test_s5_a_refusal_reaches_no_client",
        "old": '    window.assert_empty("a refusal announces nothing — announce() gates on the positive key")',
        "new": '    window.assert_kinds(["project.renamed"])  # MUTANT',
        "failing_assertion": "S5: the counted window's interior is empty — a refusal announces nothing",
    },
    {
        "pp": "PP-3",
        "signature": 'binding == "B-ALL"',
        "property": "killable names exactly the running sessions that have a runner_handle",
        "file": "tests/qa5/test_wave1_wiring.py",
        "test": "tests/qa5/test_wave1_wiring.py::test_s0_environment_truth_probe",
        "old": '    assert binding == "B-OWNED", (',
        "new": '    assert binding == "B-ALL", (  # MUTANT',
        "failing_assertion": "S0: binding == B-OWNED — KILLABLE == [S-own-1] and UNKILLABLE == [S-att-1]",
    },
    {
        "pp": "PP-4",
        "signature": 'assert pane in remaining',
        "property": "A kill_sessions delete against a real owned pane removes the pane from the tmux socket",
        "file": "tests/qa5/test_wave3_delete.py",
        "test": "tests/qa5/test_wave3_delete.py::test_s11_a_kill_that_lands_on_a_real_pane",
        "old": "    assert pane not in remaining, remaining",
        "new": "    assert pane in remaining, remaining  # MUTANT",
        "failing_assertion": "S11: the pane is no longer listed by `tmux -L shepherd-qa list-sessions` after the kill",
        "extra": ["tests/qa5/test_wave1_wiring.py::test_s0_environment_truth_probe"],
    },
    {
        "pp": "PP-5",
        "signature": 'b"QA5-S14-MARKER" not in snapshot',
        "property": "The first WebSocket frame is the pane snapshot byte-for-byte",
        "file": "tests/qa5/test_wave4_terminal.py",
        "test": "tests/qa5/test_wave4_terminal.py::test_s14_the_terminal_websocket_against_a_real_owned_pane",
        "old": '    assert b"QA5-S14-MARKER" in snapshot, (',
        "new": '    assert b"QA5-S14-MARKER" not in snapshot, (  # MUTANT',
        "failing_assertion": "S14: the first binary frame contains the pane's own bytes, including the marker the fixture wrote",
    },
    {
        "pp": "PP-6",
        "signature": 'tools == ["set_autonomy_level", "delete_project"]',
        "property": "Every gated invoke appends exactly one record to the on-disk audit log",
        "file": "tests/qa5/test_wave6_sinks.py",
        "test": "tests/qa5/test_wave6_sinks.py::test_s26_the_production_audit_sink_on_disk",
        "old": '    assert tools == ["set_autonomy_level", "set_autonomy_level", "delete_project"], tools',
        "new": '    assert tools == ["set_autonomy_level", "delete_project"], tools  # MUTANT',
        "failing_assertion": "S26: exactly three new JSONL records for the three calls under test, in order",
    },
    {
        "pp": "PP-7",
        "signature": 'result["contains"] is None',
        "property": "Each Projects pane wholly contains the box of >=1 hit-testable control, and the root reaches FILL_FLOOR",
        "file": "tests/qa5/dom.py",
        "test": "tests/qa5/test_wave5_browser.py::test_s24_intra_page_collapse_at_the_panes",
        "old": '    assert result["contains"] is not None, (',
        "new": '    assert result["contains"] is None, (  # MUTANT',
        "failing_assertion": "PANE_HEALTHY containment: the pane wholly contains the box of at least one HIT_TESTABLE descendant",
    },
    {
        "pp": "PP-8",
        "signature": 'sorted(seqs, reverse=True)',
        "property": "Frame id values are strictly monotonic, and under two concurrent writers no frame is lost or duplicated",
        "file": "tests/qa5/test_wave6_sinks.py",
        "test": "tests/qa5/test_wave6_sinks.py::test_s27_ordering_and_coalescing_under_real_concurrency",
        "old": "        assert seqs == sorted(seqs), (name, seqs)",
        "new": "        assert seqs == sorted(seqs, reverse=True), (name, seqs)  # MUTANT",
        "failing_assertion": "S27: id: values are strictly increasing at each client",
    },
    # ----- the three remediation proofs ------------------------------------
    # Beyond the per-property floor. Each one exists because the assertion it
    # sabotages was, until this round, incapable of failing — and an assertion
    # that has never been observed failing is unproven however carefully it is
    # written. The first two are the CRITICAL pair; the third is the floor that
    # makes the CONTROL_SET differential non-vacuous.
    {
        "pp": "C1-severed",
        "signature": "assert len(severed) == 0",
        "property": "S13's severed list is really populated, so the shape loop over it can execute",
        "file": "tests/qa5/test_wave3_delete.py",
        "test": "tests/qa5/test_wave3_delete.py::test_s13_orphan_moves_the_living_and_destroys_the_dead",
        "old": "    assert len(severed) == 1, (",
        "new": "    assert len(severed) == 0, (  # MUTANT",
        "failing_assertion": (
            "S13: len(severed) == 1 — exactly one cross-project lineage link is "
            "reported. A red here proves severed is NON-EMPTY; before the seed "
            "carried a real lineage pair this mutation would have SURVIVED, which "
            "is precisely the discrimination the check was missing"
        ),
        "extra": ["tests/qa5/test_wave1_wiring.py::test_s0_environment_truth_probe"],
    },
    {
        "pp": "C2-orphans",
        "signature": "assert not (running_ids <= set(cards))",
        "property": "After a reload the Flock really shows both orphans as cards under Unassigned",
        "file": "tests/qa5/test_wave3_delete.py",
        "test": "tests/qa5/test_wave3_delete.py::test_s13_orphan_moves_the_living_and_destroys_the_dead",
        "old": "    assert running_ids <= set(cards), (",
        "new": "    assert not (running_ids <= set(cards)), (  # MUTANT",
        "failing_assertion": (
            "S13: running_ids <= set(cards) — both orphaned session ids appear as "
            "[data-session-id] cards under Unassigned. The prior reading counted "
            "ids in innerText without drilling in, measured 0, asserted nothing "
            "and recorded PASS"
        ),
        "extra": ["tests/qa5/test_wave1_wiring.py::test_s0_environment_truth_probe"],
    },
    {
        "pp": "H2-nonvacuity",
        "signature": "matched NOTHING on the page the",
        "property": "A CONTROL_SET selector that stopped matching anything is caught, not silently dropped",
        "file": "tests/qa5/constants.py",
        "test": "tests/qa5/test_wave5_browser.py::test_s20_prefers_reduced_motion",
        "old": '    ("proj-new", "#proj-new"),',
        "new": '    ("proj-new", "#proj-new-renamed-by-the-mutation"),  # MUTANT',
        "failing_assertion": (
            "S20: _control_set_resolves — every CONTROL_SET selector matches >=1 "
            "element on the page its control lives on. A renamed id used to drop "
            "out of the HIT_TESTABLE differential identically to a control that "
            "is legitimately absent, producing no signal at all"
        ),
    },
]


def clear_pycache() -> None:
    for cache in REPO.rglob("__pycache__"):
        if ".venv" in cache.parts or ".claude" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def run(node_ids: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PY_BIN), "-m", "pytest", *node_ids, "-q", "--no-header", "-x", "-rf"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=2400,
        check=False,
        env={"CI": "true", "PATH": "/usr/bin:/bin", "HOME": "/root"},
    )


def classify(entry: dict, done: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """Was THIS assertion falsified, or did the run merely exit non-zero?

    **Any non-zero exit used to be recorded as `assertion_falsified`.** pytest
    exits non-zero for a collection error, a usage error, an interrupt and a
    teardown `HarnessBlocked` — none of which is evidence that the mutated check
    went false. With `-x` and a two-node-id target set, a failure in the *earlier*
    node would have been written down as the later property being proved while
    that test never ran at all.

    Four conditions, all required, and a stated reason when any fails:

    * exit status exactly 1 — the code pytest reserves for "tests failed".
      2/3/4/5 are interrupt, internal error, usage error and nothing-collected.
    * the mutated test is itself among the reported failures, not some other one.
    * the failure names the mutated assertion's own source text, so the red is
      attributable to the planted change rather than to anything else that went
      wrong in the same process.
    * the failure is not a `HarnessBlocked` — that is the environment, which is
      `blocked`, and BLOCKED never rounds to proof.
    """
    out = (done.stdout or "") + (done.stderr or "")
    if done.returncode == 0:
        return "survived", "the target passed with the mutation applied and verified live"
    if done.returncode != 1:
        return "blocked", (
            f"pytest exited {done.returncode}, which is not a test failure "
            f"(1=failed; 2=interrupted, 3=internal, 4=usage, 5=no tests collected)"
        )
    failed = [line for line in out.splitlines() if line.startswith("FAILED ")]
    if not any(entry["test"] in line for line in failed):
        return "blocked", (
            f"the mutated test is not among the failures, so the red is somebody "
            f"else's: failed={failed}"
        )
    mine = [line for line in failed if entry["test"] in line]
    if any("HarnessBlocked" in line for line in mine):
        return "blocked", f"the target failed BLOCKED, not on its assertion: {mine}"
    if entry["signature"] not in out:
        return "blocked", (
            f"the failure output does not name the mutated assertion "
            f"({entry['signature']!r}), so the red is not attributable to it"
        )
    return "assertion_falsified", ""


def targets_of(entry: dict) -> list[str]:
    """The node ids this entry runs, wave 1 first so a binding exists."""
    targets = list(dict.fromkeys([entry["test"], *entry.get("extra", [])]))
    return sorted(targets, key=lambda node: ("wave1" not in node, node))


_BASELINES: dict[tuple[str, ...], dict] = {}


def baseline_control(entry: dict) -> dict:
    """**The same target set, UNMUTATED, must be green.**

    Without it `survived` is uninterpretable and `assertion_falsified` is
    unattributable: a target set that is red before anything is planted produces
    a red afterwards too, and the driver would write down a proof it did not
    earn. Cached per target set, because eight of the nine entries name the same
    node ids as each other or as nobody.
    """
    targets = tuple(targets_of(entry))
    if targets in _BASELINES:
        return _BASELINES[targets]
    clear_pycache()
    done = run(list(targets))
    control = {
        "targets": list(targets),
        "exit_code": done.returncode,
        "green": done.returncode == 0,
        "output_tail": (done.stdout or "")[-1500:],
    }
    _BASELINES[targets] = control
    print(f"baseline {list(targets)}: {'green' if control['green'] else 'RED'}", flush=True)
    return control


def main() -> int:
    only = sys.argv[1:] or [entry["pp"] for entry in MUTATIONS]
    results = []
    for entry in MUTATIONS:
        if entry["pp"] not in only:
            continue
        control = baseline_control(entry)
        path = REPO / entry["file"]
        original = path.read_text()
        assert entry["old"] in original, f"{entry['pp']}: target line not found in {entry['file']}"
        assert original.count(entry["old"]) == 1, f"{entry['pp']}: target line is not unique"
        try:
            path.write_text(original.replace(entry["old"], entry["new"]))
            clear_pycache()
            applied = subprocess.run(
                ["git", "-C", str(REPO), "diff", "--no-index", "--stat", "/dev/null", str(path)],
                capture_output=True, text=True, check=False,
            )
            evidence_cmd = f"grep -n 'MUTANT' {entry['file']}"
            evidence = subprocess.run(
                ["grep", "-n", "MUTANT", entry["file"]],
                cwd=REPO, capture_output=True, text=True, check=False,
            )
            assert evidence.returncode == 0 and evidence.stdout.strip(), "the mutation did not land"
            targets = targets_of(entry)
            done = run(targets)
            outcome, reason = classify(entry, done)
            if not control["green"]:
                outcome, reason = "blocked", (
                    f"the unmutated baseline for {control['targets']} exited "
                    f"{control['exit_code']}; nothing measured against it is "
                    f"attributable to the mutation"
                )
            tail = (done.stdout or "")[-2500:]
            row = {
                "pp": entry["pp"],
                "property": entry["property"],
                "targets": entry["failing_assertion"],
                "applied_evidence": f"$ {evidence_cmd}\n{evidence.stdout.strip()}",
                "outcome": outcome,
                "failing_assertion": entry["failing_assertion"],
                "exit_code": done.returncode,
                "node_ids": targets,
                "baseline_control": control,
                "output_tail": tail,
            }
            if outcome == "blocked":
                row["blocked_reason"] = reason
            results.append(row)
            print(f"{entry['pp']}: {outcome} (exit {done.returncode}) {reason}", flush=True)
        finally:
            path.write_text(original)
            clear_pycache()
            assert path.read_text() == original, f"{entry['pp']}: revert failed"
    # **The generator writes the file the report names.** It used to write
    # `results.json` while the published artifact was `qa5-mutation-checks.json`,
    # so re-running the named generator did not reproduce the named capture —
    # and regenerability is the condition CLAUDE.md sets for a capture to count
    # as evidence at all.
    out = Path(__file__).parent / "qa5-mutation-checks.json"
    existing = json.loads(out.read_text()) if out.exists() else []
    by_pp = {item["pp"]: item for item in existing}
    for item in results:
        by_pp[item["pp"]] = item
    out.write_text(json.dumps([by_pp[k] for k in sorted(by_pp)], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
