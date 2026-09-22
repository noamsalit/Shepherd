"""Clause 16 — no test M1–M3 shipped has been deleted or weakened.

The baseline is `tests/boundaries/collected_node_ids.txt`, frozen at step 0b
row 10 by the **corrected** command (`pytest --collect-only -q -o addopts='-m
"not live"'` — `pyproject.toml`'s own `addopts` already carries `-q`, and a
second one makes it `-qq`, which prints per-file counts rather than node ids).
This module re-runs that command and asserts the frozen set is a **subset** of
the live one, with every absence named.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "collected_node_ids.txt"

COLLECT_ARGV = (
    sys.executable,
    "-m",
    "pytest",
    "--collect-only",
    "-q",
    "-o",
    "addopts=-m 'not live'",
)

#: Node ids frozen at step 0b that are **deliberately** gone from the live tree,
#: each with its reason and the decision that authorised it. Clause 16 expects
#: this to be empty; it is not, and the entry says why rather than the clause
#: being quietly widened.
RETIRED_NODE_IDS: Mapping[str, tuple[str, str]] = {
    "tests/toolsurface/test_registry.py::test_no_authorize_call_exists_yet": (
        "M1's tripwire: it walked every identifier under toolsurface/ and asserted "
        "'authorize' and 'audit_log' were absent, so that M4's addition would be visible "
        "in the diff. T6 put authorize() and the audit write inside invoke() — the event "
        "the tripwire watches for. It is retired rather than narrowed because it would "
        "have stayed GREEN after T6 (the call goes through a local named 'authorizer' and "
        "AuditRecord/AuditSink/_audit), and a tripwire that is green after the event it "
        "watches for reads as evidence the event did not happen. The property is now "
        "asserted positively by tests/toolsurface/test_registry_gate.py::"
        "test_no_handler_runs_before_the_gate_answers and "
        "test_every_blast_class_audits_exactly_once.",
        "RD-T4-4 (router decision: 'M1's test_no_authorize_call_exists_yet must be retired "
        "by T6, out loud'), applied by T6 and recorded in docs/plans/m4-blockers/t6.md "
        "section T6-1.",
    ),
    "tests/store/test_migration_003.py::test_future_schema_refuses_to_start_at_four": (
        "The test builds its impossible sentinel by inserting a schema_migration row at "
        "version 4, and migration 004 makes 4 the real current version. Because "
        "schema_migration.version is INTEGER PRIMARY KEY (001_m1_foundation.sql:22), that "
        "insert became a primary-key collision inside the test's own setup rather than the "
        "future-schema refusal it asserts, so the test could no longer observe the rule it "
        "was written for. The rule itself is unchanged and is re-proved one version up by "
        "the named successor in the same module, "
        "test_future_schema_refuses_to_start_at_five, which inserts version 5.",
        "§7 rule 2, re-anchored by §3 D57's migration 004.",
    ),
}


def node_ids(transcript: str, source: str) -> frozenset[str]:
    """Node ids out of a `--collect-only -q` transcript.

    Arrival before absence, on **both** sides: an empty baseline makes the
    subset compare true for every live tree, and an empty live set makes it
    false for every baseline — but the transcript that produces an empty live
    set is the `-qq` one (per-file counts, no node ids), which is the exact
    defect step 0b row 10 was corrected for. Either way the compare has stopped
    deciding anything, so the parse refuses to hand back nothing.
    """
    ids = frozenset(line.strip() for line in transcript.splitlines() if "::" in line.strip())
    assert ids, (
        f"{source} parsed to no node ids at all — a compare against nothing "
        "cannot fail (is the collection command doubling -q?)"
    )
    return ids


def baseline_node_ids(path: Path = BASELINE) -> frozenset[str]:
    """The set frozen at step 0b row 10."""
    assert path.is_file(), f"the clause-16 baseline is unreadable: {path}"
    return node_ids(path.read_text(), f"the clause-16 baseline {path}")


def live_node_ids() -> frozenset[str]:
    """Collect the live tree with step 0b row 10's corrected command."""
    done = subprocess.run(
        COLLECT_ARGV, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600
    )
    assert done.returncode == 0, f"collection failed ({done.returncode}): {done.stdout[-2000:]}"
    return node_ids(done.stdout, "the live collection")


def subset_violations(
    baseline: frozenset[str],
    live: frozenset[str],
    retired: Mapping[str, tuple[str, str]],
) -> list[str]:
    """Every way the frozen set can fail to be a subset of the live one."""
    found: list[str] = []
    missing = baseline - live
    unexplained = sorted(missing - set(retired))
    if unexplained:
        found.append(f"node ids frozen at step 0b are gone with no recorded decision: {unexplained}")
    stale = sorted(set(retired) - missing)
    if stale:
        found.append(
            "stale exemptions — these node ids are not missing from the live tree, so "
            f"the entry is an exemption for a deletion that did not happen: {stale}"
        )
    return found


@pytest.fixture(scope="module")
def live() -> frozenset[str]:
    """One collection subprocess for the module, not one per test."""
    return live_node_ids()


def test_an_empty_baseline_is_not_a_passing_compare(tmp_path: Path) -> None:
    """Arrival before absence: a subset compare against nothing cannot fail."""
    empty = tmp_path / "collected_node_ids.txt"
    empty.write_text("\n\n1480/1517 tests collected (37 deselected) in 0.90s\n")
    with pytest.raises(AssertionError, match="no node ids"):
        baseline_node_ids(empty)


def test_an_unreadable_baseline_is_not_a_passing_compare(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="unreadable"):
        baseline_node_ids(tmp_path / "moved_away.txt")


def test_a_stale_exemption_is_caught(live: frozenset[str]) -> None:
    """An exemption for a test that is still there is how this list rots."""
    baseline = baseline_node_ids()
    still_collecting = sorted(baseline & live)[0]
    never_frozen = "tests/nowhere.py::test_that_was_never_in_the_baseline"
    rot = {
        **RETIRED_NODE_IDS,
        still_collecting: ("reason", "decision"),
        never_frozen: ("reason", "decision"),
    }
    found = subset_violations(baseline, live, rot)
    assert len(found) == 1, found
    assert "stale" in found[0]
    assert still_collecting in found[0]
    assert never_frozen in found[0]


def test_every_node_id_frozen_at_step_0b_still_collects(live: frozenset[str]) -> None:
    assert subset_violations(baseline_node_ids(), live, RETIRED_NODE_IDS) == []


def test_a_second_deletion_is_caught(live: frozenset[str]) -> None:
    """The negative control: without it, the subset compare is decorative."""
    baseline = baseline_node_ids()
    victim = sorted(baseline & live)[0]
    found = subset_violations(baseline, live - {victim}, RETIRED_NODE_IDS)
    assert len(found) == 1, found
    assert "no recorded decision" in found[0]
    assert victim in found[0]


def test_a_doubled_q_transcript_cannot_pass_as_a_collection() -> None:
    """What `-qq` actually prints — per-file counts, no node ids (T1-1)."""
    doubled_q = "tests/boundaries/test_layer_direction.py: 9\ntests/web/test_ws.py: 21\n"
    with pytest.raises(AssertionError, match="doubling -q"):
        node_ids(doubled_q, "a -qq transcript")


def test_every_retirement_names_its_reason_and_the_decision_that_authorised_it() -> None:
    """A bare exemption list is an exemption list that rots."""
    assert RETIRED_NODE_IDS, "the exception list is empty — see clause 16 and RD-T4-4"
    for node_id, (reason, decision) in RETIRED_NODE_IDS.items():
        assert "::" in node_id, node_id
        assert len(reason) > 80, f"{node_id} has no reason worth the name"
        assert "RD-" in decision or "§" in decision, (
            f"{node_id}'s retirement names no decision that authorised it"
        )
