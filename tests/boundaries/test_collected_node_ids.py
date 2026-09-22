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
    "tests/web/test_routes_m3.py::test_no_body_field_shadows_a_path_parameter": (
        "The name says `body`, and the property is now both tables. It enumerated two "
        "names — `routes.SESSION_ID` and `routes.PROJECT_ID` — and checked them against "
        "every template's `BODY_ARGS`: two of the three path parameters this table has, "
        "with `approval_id` covered by a comment and nothing else, and keyed on constants "
        "no production code reads, so a typo in one of them made the assertion vacuous and "
        "green. It is renamed rather than edited in place because the subject changed: the "
        "successor derives each template's `{…}` segments from the template itself, so it "
        "cannot miss a parameter or go vacuous, and it applies the same loop to "
        "`QUERY_ARGS`, which nothing checked at all. Re-proved by the named successor in "
        "the same file, test_no_declared_field_shadows_a_path_parameter, whose gate is seen "
        "to fail by test_the_shadow_guard_catches_the_parameter_the_enumeration_missed.",
        "P13/M1's invariant is unchanged; the retirement is recorded per §0 in "
        "docs/plans/projects-ui-blockers/t3-4-remfix.md (T3.4 remediation).",
    ),
    "tests/toolsurface/test_tools_m3.py::test_the_three_modules_are_each_under_the_cap": (
        "The name is the defect. It built `sizes` from an explicit seven-path tuple and "
        "asserted `len(sizes) == 7`, so an eighth `tools_*.py` was simply not in the tuple: "
        "the count still passed and the new module was measured by nothing — a gate whose "
        "subject is a list somebody has to remember to extend certifies the modules somebody "
        "remembered. It is renamed rather than edited in place because the enumeration was "
        "the whole of its method and because the glob found four modules it had never "
        "measured at all (tools_engine, tools_hooks, tools_replay, and two over the cap), so "
        "a reader who sees the old name in a log is looking at a different property. The cap "
        "is unchanged and is re-proved over every module by the named successor in the same "
        "file, test_every_tool_module_is_under_the_cap, which globs the package and keeps an "
        "explicit count so a new module must be admitted; its gate is seen to fail by "
        "test_the_cap_gate_measures_a_module_the_enumeration_would_have_missed.",
        "Task 18's cap is unchanged; the retirement is recorded per §0 in "
        "docs/plans/projects-ui-blockers/t3-4-remfix.md (T3.4 remediation).",
    ),
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
    "tests/store/test_store_delegation.py::test_upsert_workspace_updates_a_moved_root_path": (
        "The test pinned upsert_workspace's middle arm — update a changed root_path — and "
        "migration 004 removes both the column and the verb: workspace.root_path is dropped "
        "and upsert_workspace is deleted by RD-1, because a project keyed by name made "
        "/work/api and /personal/api one row and let the second silently overwrite the "
        "first's path. The property it protected — that a moved path updates the existing "
        "repo row rather than minting a second under ux_repo_path — moved to add_repo and "
        "is asserted by the named successor "
        "tests/store/test_verbs.py::test_re_adding_an_orphaned_path_rebinds_the_same_repo_row.",
        "§3 D57.",
    ),
    "tests/signals/test_discovery.py::test_discovery_finds_worktree_with_dotgit_file": (
        "discover_repos existed to walk workspace.root_path — the module's own first line says so — and migration 004 drops that column, so the module's sole documented justification is gone. It had no caller anywhere in src/ at any point, and U14 has repo paths typed into the Edit dialog rather than scanned for, so wiring it now would mean building a caller in order to justify a module. Deleted with its suite rather than left as dead code that the next reader has to re-decide; probe_repo and resolve_remote, which binding.py imports, are untouched.",
        "§3 D57 / RD-2.",
    ),
    "tests/signals/test_discovery.py::test_discovery_skips_non_repo_directories": (
        "discover_repos existed to walk workspace.root_path — the module's own first line says so — and migration 004 drops that column, so the module's sole documented justification is gone. It had no caller anywhere in src/ at any point, and U14 has repo paths typed into the Edit dialog rather than scanned for, so wiring it now would mean building a caller in order to justify a module. Deleted with its suite rather than left as dead code that the next reader has to re-decide; probe_repo and resolve_remote, which binding.py imports, are untouched.",
        "§3 D57 / RD-2.",
    ),
    "tests/signals/test_discovery.py::test_discovery_of_a_directory_with_no_repos_is_empty": (
        "discover_repos existed to walk workspace.root_path — the module's own first line says so — and migration 004 drops that column, so the module's sole documented justification is gone. It had no caller anywhere in src/ at any point, and U14 has repo paths typed into the Edit dialog rather than scanned for, so wiring it now would mean building a caller in order to justify a module. Deleted with its suite rather than left as dead code that the next reader has to re-decide; probe_repo and resolve_remote, which binding.py imports, are untouched.",
        "§3 D57 / RD-2.",
    ),
    "tests/orchestration/test_admission.py::test_a_repo_registered_outside_its_workspace_root_is_admitted": (
        "The test's whole premise is a repo registered OUTSIDE its workspace root, and migration 004 drops workspace.root_path — so after D57 every repo is outside it, because there is no it, and the assertion can no longer distinguish the defect it was written for from the ordinary case. The property it protected — a registered repo path admits a spawn into itself and into a directory under it — is asserted by the named successor in the same file, test_a_registered_repo_admits_a_spawn.",
        "§3 D57.",
    ),
    "tests/orchestration/test_admission.py::test_a_workspace_with_no_root_path_still_admits_its_registered_repos": (
        "The name states a condition that cannot be expressed any more: root_path is dropped by migration 004, so every project has no root path and the test's distinguishing setup is gone. What it proved — that the allowlist is the registered repos and the spawn is admitted on their strength alone — is asserted by the named successor in the same file, test_add_repo_widens_the_allowlist, which measures the allowlist across the one registration rather than asserting it once afterwards.",
        "§3 D57.",
    ),
    "tests/orchestration/test_admission.py::test_the_workspace_root_stays_a_permitted_root_beside_the_repos": (
        "This test asserted the opposite of what D57 decides: the workspace root was a permitted root beside the repo paths, and after migration 004 the population is the registered repo paths ALONE. It is retired rather than inverted because a test whose name promises the root stays and whose body proves it is gone is a trap for the next reader. The new rule's boundary is asserted by the named successor in the same file, test_a_project_with_no_repo_refuses_everything.",
        "§3 D57.",
    ),
    "tests/orchestration/test_admission.py::test_a_workspace_with_neither_a_root_nor_a_repo_refuses_everything": (
        "Half the condition in the name — 'neither a root' — stopped existing when migration 004 dropped workspace.root_path, so the test now describes a two-part setup of which only one part can be built. The property is unchanged and is the whole of the named successor in the same file, test_a_project_with_no_repo_refuses_everything: an empty allowlist is a refusal and never permission, asserted for an ordinary project and for the reserved one.",
        "§3 D57.",
    ),
    "tests/web/test_rail.py::test_rail_is_on_every_page": (
        "This is the assertion D66 reverses, and it is the reason the row exists: it read "
        "index.html for an id=\"rail\" slot positioned before <main> in order to prove the rail "
        "was the shell rather than one view's child, which is exactly what §12 specified and "
        "what the owner has now decided against. The rail leaves the shell; if it returns it "
        "lives on the Flock page alone (U2), so there is no shell slot left for this test to "
        "find and no narrowed form of it that would still be true. Retired with its decision "
        "written in the same task, per §0, rather than deleted as an inconvenient failure.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_rail_shows_the_actual_ask": (
        "Two halves, and only the renderer half dies. The payload half asserted that "
        "fleet_summary's needs_you list carries the fold's own needs_you_reason, and that half "
        "is re-proved at the projection seam by tests/qa/test_s4_needs_you_rail.py::"
        "test_the_rail_carries_a_row_per_blocked_session_with_its_own_ask, which drives two "
        "sessions in with different asks so a repeated reason is caught. The other half scanned "
        "rail.js for renderRail and for the absence of the forbidden category wording, and D66 "
        "takes that renderer off the shell, so the scan is of a module the shell no longer loads.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_idle_prompt_is_needs_you_and_the_rail_says_idle": (
        "C21's wording rule, asserted through the rail's HTTP payload: idle_prompt flips an idle "
        "TUI to needs_you 60 s after a Stop, and the row must read 'idle — waiting for your next "
        "instruction' rather than a category. The rule is about what the fold composes, not about "
        "where it is drawn, and D66 removes only the drawing. The surviving assertion of the same "
        "property is at the projection: tests/qa/test_s4_needs_you_rail.py compares every row's "
        "needs_you_reason against the exact text its own source wrote, which is the same check "
        "one layer below the renderer that has left.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_rail_renders_with_a_null_reason": (
        "Principle 5 on a missing ask — unknown, never a blank row and never an invented one. The "
        "projection half (a needs_you row whose needs_you_reason is None is still a row) is a "
        "property of project_needs_you and survives; what cannot survive is the other half, a "
        "regex over rail.js for a named RAIL_UNKNOWN_ASK fallback constant whose wording is "
        "checked for 'unknown' or 'not recorded'. D66 takes the renderer off the shell, so its "
        "fallback string is no longer a thing any page displays, and a scan asserting the wording "
        "of text nobody reads is a green that means nothing.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_empty_rail_collapses_to_a_line": (
        "§12's empty state: a 4 px green line rather than an empty panel announcing nothing, in "
        "the same finished green as the chip, read out of app.css's .rail-empty rule and "
        "cross-checked against core.stops.PALETTE. D66 removes the rail from the shell and T5.2 "
        "rewrites app.css for the new one, so .rail-empty is a rule for a component with no "
        "mount point. The palette-is-the-one-source property this leaned on is independently "
        "held by tests/web/test_palette.py, which parses every .bucket-<name> rule back out of "
        "the stylesheet and compares it against PALETTE.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_rail_updates_from_sse_not_polling": (
        "§12's no-polling rule, asserted by scanning rail.js for setInterval, setTimeout, "
        "requestAnimationFrame and fetch( and by checking app.js drives the redraw from "
        "onEnvelope. The rule is not retired with the test — it is a property of the whole UI, "
        "and the stream half of it is held by the EventSource assertion in sse.js's own coverage "
        "— but the module this scanned is the rail renderer D66 takes off the shell, and the "
        "app.js half names an import (./rail.js) that the new shell does not make. Re-anchor any "
        "future rail on the Flock page's own no-polling scan rather than on this one.",
        "§3 D66",
    ),
    "tests/web/test_rail.py::test_rail_says_unknown_before_the_fleet_has_been_read": (
        "The rail's own third state: not-read-yet is not empty, because a green line is a claim "
        "that nothing is waiting on you and nobody has established that before the first "
        "fleet_summary lands. The property is real and it survives at the projection, where "
        "tests/qa/test_s4_needs_you_rail.py::test_an_empty_rail_is_distinguishable_from_an_unread_one "
        "drives both states and asserts [] and None are different values. What is retired is its "
        "rendering: an index.html slot carrying rail-unknown and a .rail-unknown CSS rule in the "
        "unclassified grey, both of which D66 takes off the shell.",
        "§3 D66",
    ),
    "tests/web/test_fleet_page.py::test_stopped_row_renders_why_and_first_action": (
        "The test asserts stoppedRow renders session-why and actions[0], and U7 fixes the card "
        "at four items — glyph, title, the ask, relative time — so after the redesign no row "
        "renders either; the property survives at the pane and is asserted by its named "
        "successor test_the_session_pane_renders_why_and_every_action. The successor is "
        "strictly stronger rather than equivalent: the collapsed fleet row had space for one "
        "action and rendered actions[0], while the pane renders every action with its ordinal "
        "and its source, so what retires is the truncation and not the rule. D67 relocates the "
        "session view into the Flock's third pane, and §12 already placed D21's next_actions "
        "list in that view's header, which is why there is somewhere for the list to go.",
        "§12 (the Session view header already carries the list) with §3 D67",
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
