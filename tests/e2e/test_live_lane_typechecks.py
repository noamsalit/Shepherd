"""The live lane's static net — and it runs in the **default** lane, not the live one.

**This module carries no `pytest.mark.live`, and that is the whole point.**

A test the default run deselects is not a failing test; it is an absent one. So a
module in the live lane can carry a plain `TypeError` — a call whose arity no
longer matches, a name that no longer exists, an import that no longer
resolves — and stay green for as long as nobody runs `-m live`. That is not a
hypothetical: **T8-3 made `make_run_argv`'s `commands` argument required on
2026-09-17 and `tests/contracts/test_runner_contract.py` kept calling it with one
argument for hours.** `mypy --strict` did not see it, because that profile runs
over `src/` only; the default `pytest` did not see it, because `addopts` is
`-m 'not live'`. Two nets, and the module fell between them.

This is the net for that gap. It type-checks exactly **the files the default run
does not execute** — derived by asking pytest which node ids `-m live` selects,
never from a list somebody maintains — plus the `conftest.py` beside each of
them, because a shared fixture module is where an arity change lands hardest and
it contains no tests of its own to be collected.

**It is not `--strict`.** `mypy --strict tests` is 233 errors in 108 files; a gate
that large is a gate that gets an exemption bolted on within a week. The profile
is `live_lane_mypy.ini` beside this file, and its docstring says why each setting
is what it is. The class of defect it exists to catch — arity, names, imports —
is caught at every strictness level, which is why the weaker profile costs the
net nothing it was built for.

**Self-checks, because a scan of nothing finds nothing.** The derived set is
asserted non-empty, asserted disjoint from what the default run selects (or the
gate would be checking files pytest already executes, which is a different and
much weaker claim), and asserted to be real files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The profile, beside this file. Never `pyproject.toml`'s — see that file's note.
CONFIG = Path(__file__).resolve().parent / "live_lane_mypy.ini"

#: How long the two subprocesses get. A ceiling, not a measurement.
CEILING_S = 600.0


def collected(marker: str) -> set[str]:
    """Every node id pytest selects under `-m <marker>`.

    A subprocess rather than an in-process collection: this module is itself
    inside the tree being collected, and re-entering pytest from a running test
    is how a collection hook ends up observing its own run.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            # `addopts` carries `-m 'not live'`, and under it `--collect-only -q`
            # prints a per-file **count** instead of node ids. Cleared here so the
            # answer is the node ids this parser reads, and the marker is then
            # the only selector in play.
            "-o",
            "addopts=",
            "-m",
            marker,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=CEILING_S,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    found: set[str] = set()
    for line in completed.stdout.splitlines():
        head, separator, _ = line.partition("::")
        if not separator or not head.endswith(".py"):
            continue
        found.add(line.strip())
    return found


def files(node_ids: set[str]) -> set[Path]:
    """The files those node ids live in."""
    return {Path(node_id.partition("::")[0]) for node_id in node_ids}


def live_lane_targets(live_ids: set[str]) -> set[Path]:
    """The gate's **derived target set**: what it type-checks, as paths.

    The files `-m live` selects, plus the `conftest.py` beside each of them — a
    shared fixture module carries no test of its own, so it never appears in any
    collection, and it is exactly where an arity change lands hardest.

    One definition, read by both checks below. Two spellings of *"what this gate
    covers"* is RD-T5-5's shape: a set that can be widened in one place and keep
    reporting the old answer from the other.
    """
    deselected = files(live_ids)
    return {*deselected, *{relative.parent / "conftest.py" for relative in deselected}}


#: T26 (**P-M4-18**). M4's own live modules, which must be **inside** the set
#: the gate derives. Written out here rather than derived, deliberately: the
#: derivation is the thing under test, so an expectation derived the same way
#: would agree with it by construction and could never disagree. K21's whole
#: point is that *a net that silently stopped covering them is the same defect
#: one layer out* — the `TypeError` that sat in the live lane for hours.
M4_LIVE_MODULES: frozenset[Path] = frozenset(
    {
        Path("tests/e2e/test_live_master.py"),
        Path("tests/e2e/test_live_master_isolation.py"),
        Path("tests/e2e/conftest.py"),
    }
)


def test_every_module_the_default_run_deselects_still_type_checks() -> None:
    """The gate. Red on an arity change, a renamed symbol or a dead import.

    Ordered so that nothing is asserted about a population before the population
    is shown to be real: the deselected set is non-empty, it is disjoint from
    what the default run executes, every member exists on disk — and only then is
    the type checker run over it.
    """
    live_ids = collected("live")
    default_ids = collected("not live")

    assert live_ids, (
        "pytest selects no live tests at all, so this gate would check nothing — "
        "either the marker was renamed or the lane was deleted"
    )
    # Disjoint at the **node id**, which is where the marker actually applies.
    # Three modules — `tests/contracts/test_runner_contract.py` among them —
    # carry live and ordinary tests side by side, and that module is precisely
    # where T8-3's arity break sat: the file imports, the ordinary tests run, and
    # the live test's body is never executed. A file-level disjointness rule
    # would have excluded the one file this gate was built for.
    assert live_ids.isdisjoint(default_ids), sorted(live_ids & default_ids)
    assert default_ids, "the default run selects nothing, so the comparison is empty"

    deselected = files(live_ids)
    for relative in deselected:
        assert (REPO_ROOT / relative).is_file(), relative

    # The `conftest.py` beside each of them: a shared fixture module carries no
    # test of its own, so it never appears in a collection — and it is exactly
    # where `make_run_argv(permitted, commands)` is called from.
    targets = sorted(live_lane_targets(live_ids))
    present = [relative for relative in targets if (REPO_ROOT / relative).is_file()]
    assert len(present) >= len(deselected), (targets, present)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(CONFIG),
            *[str(relative) for relative in present],
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=CEILING_S,
    )
    assert completed.returncode == 0, (
        "the live lane does not type-check, so a module the default run never "
        "executes may not even import:\n" + completed.stdout + completed.stderr
    )
    # …and the checker really opened them: a `mypy` given no files also exits 0.
    assert "no issues found in" in completed.stdout, completed.stdout
    checked = int(completed.stdout.split("no issues found in")[1].split()[0])
    assert checked >= len(present), (checked, present)


def test_the_live_net_covers_the_m4_modules() -> None:
    """**P-M4-18**, T26. The gate's derived set **contains** M4's live modules.

    K21 says M4's new live modules inherit the net *"for free"*, and this is the
    check that the word "free" is earned. The gate above proves the derivation
    type-checks whatever it found; it says nothing about **what** it found. A
    derivation that stopped seeing `tests/e2e/` — a renamed marker, a moved
    package, a collection that silently returns fewer node ids — would keep
    passing that gate over the remaining files while M4's modules sat outside
    it, and *that is exactly how a `TypeError` sat in the live lane for hours*.
    So the emptiness check is not enough and neither is disjointness: this
    asserts membership.

    Ordered arrival-first, because a containment over an empty set is vacuous:
    the derived set is shown non-empty, each expected module is shown to be a
    real file on disk, and only then is containment asserted.
    """
    targets = live_lane_targets(collected("live"))

    assert M4_LIVE_MODULES, (
        "this check's own expectation is empty, so the containment below would"
        " be true of any derived set at all — including one that covers nothing"
    )
    assert targets, (
        "the live-lane gate derives no targets at all, so its coverage claim is"
        " over nothing — either the marker was renamed or the lane was deleted"
    )
    for relative in sorted(M4_LIVE_MODULES):
        assert (REPO_ROOT / relative).is_file(), (
            f"{relative} is not on disk, so asserting the net covers it would be"
            " asserting something about a file that does not exist"
        )

    assert M4_LIVE_MODULES <= targets, {
        "not covered": sorted(M4_LIVE_MODULES - targets),
        "covered": sorted(targets),
    }
