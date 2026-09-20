"""`tests/conftest.py`'s own `/tmp/shp-<uid>` policy, asserted rather than assumed.

Two properties, and they pull against each other, which is why both are here.

**Retention.** The base pytest hands this suite is chosen by `conftest.py`, and
whatever chooses it also has to clean up after it. Until 2026-09-20 the only
bound was age — 24 h — and nothing removed a base at session end, so one day of
work left **2.8 GB across 155 run directories**. The reason it was age-only is
real and is preserved here: several tests run pytest as a subprocess
(`tests/boundaries/test_collected_node_ids.py` collects the whole tree in a
child), so more than one run of this conftest is live at once, and a plain
"keep the newest three" had each child delete its *parent's* base out from under
it. That argues for a **floor**, not against a **ceiling**. So the policy is
both: nothing inside the grace window is ever touched, and past it the newest N
survive. `test_a_base_inside_the_grace_window_survives_the_count_cap` is the
regression test for the concurrency bug; the two after it are the ceiling.

That pair bounds the tree in **steady state** and cannot bound a **burst**: the
prune is lazy (it runs from the next session's `pytest_configure`) and nothing
inside the grace window is a candidate, so a tight loop of runs keeps its whole
population inside the window — measured 2026-09-20 at 1.3 GB across 64 bases in
18 minutes. `remove_own_run` is the eager half, and the four tests at the end of
this module are its property: a finished run removes the one base it created
and cannot reach any other, so the floor above survives unchanged.

**Ownership.** `/tmp` is world-writable and sticky, and this tree runs as root
on Linux. `mkdir(mode=0o700, exist_ok=True)` accepts a *pre-existing* directory
whatever its owner and mode, and `os.access(W_OK)` answers True for root no
matter who owns it — so an unprivileged local user who pre-creates `/tmp/shp-0`
gets a directory a root pytest then fills with fixtures and prunes inside. The
root must be ours and ours alone, or it is not used at all.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import conftest as suite_conftest


def make_run(root: Path, name: str, age_s: float) -> Path:
    """A run base `age_s` seconds old, as `prune_old_runs` will see it."""
    base = root / name
    base.mkdir()
    (base / "marker").write_text(name)
    stamp = time.time() - age_s
    os.utime(base, (stamp, stamp))
    return base


def test_a_base_inside_the_grace_window_survives_the_count_cap(tmp_path: Path) -> None:
    """The concurrency floor: a live child pytest's base is never collected.

    Six bases, all newly created, a cap of two. A count-only rule keeps two and
    deletes four — which is the `FileNotFoundError` inside pytest's own
    `find_prefixed` that made this policy age-only in the first place. The
    grace window must win over the cap, not lose to it.
    """
    bases = [make_run(tmp_path, f"run{index}", age_s=0.0) for index in range(6)]

    suite_conftest.prune_old_runs(
        tmp_path, retention_s=24 * 3600, grace_s=900.0, keep_newest=2
    )

    survivors = sorted(base.name for base in bases if base.exists())
    assert survivors == sorted(base.name for base in bases), (
        "a base younger than the grace window was deleted; a concurrent pytest's "
        f"base is by definition recent. Survivors: {survivors}"
    )


def test_beyond_the_grace_window_only_the_newest_n_survive(tmp_path: Path) -> None:
    """The ceiling: 155 bases and 2.8 GB is what age-alone permits."""
    ages = {"oldest": 5000.0, "older": 4000.0, "old": 3000.0, "newer": 2000.0}
    for name, age_s in ages.items():
        make_run(tmp_path, name, age_s=age_s)

    suite_conftest.prune_old_runs(
        tmp_path, retention_s=24 * 3600, grace_s=60.0, keep_newest=2
    )

    survivors = sorted(child.name for child in tmp_path.iterdir())
    assert survivors == ["newer", "old"], (
        f"expected the newest two by mtime past the grace window, got {survivors}"
    )


def test_a_base_older_than_retention_goes_even_inside_the_count_cap(
    tmp_path: Path,
) -> None:
    """Age is still a bound in its own right, not merely a tie-break."""
    make_run(tmp_path, "ancient", age_s=48 * 3600)
    make_run(tmp_path, "recent", age_s=3000.0)

    suite_conftest.prune_old_runs(
        tmp_path, retention_s=24 * 3600, grace_s=60.0, keep_newest=10
    )

    survivors = sorted(child.name for child in tmp_path.iterdir())
    assert survivors == ["recent"], survivors


def test_a_root_we_own_and_only_we_can_reach_is_accepted(tmp_path: Path) -> None:
    """The happy path, so the refusals below are not vacuous (B1)."""
    root = suite_conftest.short_temproot(parent=tmp_path, name="shp-test")
    assert root == tmp_path / "shp-test"
    assert root is not None
    assert root.is_dir()
    assert root.stat().st_mode & 0o077 == 0


def test_a_root_owned_by_another_user_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/tmp` is world-writable: the directory may be someone else's trap.

    `os.access(root, W_OK)` cannot see this — as root it answers True for every
    directory on the system, which is precisely the case that matters.
    """
    (tmp_path / "shp-test").mkdir(mode=0o700)
    someone_else = os.getuid() + 1
    monkeypatch.setattr(os, "getuid", lambda: someone_else)

    assert suite_conftest.short_temproot(parent=tmp_path, name="shp-test") is None


@pytest.mark.parametrize("mode", [0o777, 0o770, 0o707, 0o750, 0o705])
def test_a_root_reachable_by_group_or_other_is_refused(tmp_path: Path, mode: int) -> None:
    """Any bit outside the owner triad disqualifies it, not just write."""
    root = tmp_path / "shp-test"
    root.mkdir()
    root.chmod(mode)

    assert suite_conftest.short_temproot(parent=tmp_path, name="shp-test") is None


def test_a_root_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    """`lstat`, not `stat`: a symlink to a directory we own is not our directory."""
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    (tmp_path / "shp-test").symlink_to(target)

    assert suite_conftest.short_temproot(parent=tmp_path, name="shp-test") is None


def test_session_finish_removes_this_runs_own_base(tmp_path: Path) -> None:
    """The burst bound: a run deletes its own base rather than waiting to be pruned.

    `prune_old_runs` is lazy (it runs from the *next* session's
    `pytest_configure`) and grace-bounded (nothing younger than 15 minutes is a
    candidate), so a tight loop of runs — which `CLAUDE.md` rule 4 mandates —
    keeps its whole population inside the grace window. Measured on 2026-09-20:
    1.3 GB across 64 bases created inside 18 minutes. A session knows it has
    finished, which is the fact `mtime` is being used to guess at.
    """
    own = tmp_path / "own"
    own.mkdir()
    (own / "fixture").write_text("payload")

    suite_conftest.remove_own_run(own, failed=0)

    assert not own.exists(), "the run that created this base did not remove it"


def test_session_finish_removes_nothing_but_its_own_base(tmp_path: Path) -> None:
    """The concurrency floor, restated for the eager path.

    `prune_old_runs` protects a live child pytest with a grace window. This
    path needs no window because it never enumerates: it is handed exactly one
    path — the one this process created in `pytest_configure` — and a child
    pytest's base is a different `mkdtemp` result. Two fresh siblings stand in
    for a concurrent child here, and the removal must not be able to see them.
    """
    own = tmp_path / "own"
    child = tmp_path / "child-pytest"
    sibling = tmp_path / "another-run"
    for base in (own, child, sibling):
        base.mkdir()
        (base / "fixture").write_text(base.name)

    suite_conftest.remove_own_run(own, failed=0)

    survivors = sorted(base.name for base in tmp_path.iterdir())
    assert survivors == ["another-run", "child-pytest"], survivors


def test_a_failed_run_keeps_its_base_for_the_post_mortem(tmp_path: Path) -> None:
    """The reason the bases exist at all: a red run's fixtures are evidence."""
    own = tmp_path / "own"
    own.mkdir()
    (own / "fixture").write_text("payload")

    suite_conftest.remove_own_run(own, failed=1)

    assert own.is_dir(), "a failed run's base was removed before anyone could read it"


def test_a_run_that_did_not_choose_its_own_base_removes_nothing(tmp_path: Path) -> None:
    """`--basetemp=...` from the caller is the caller's directory, not ours."""
    given = tmp_path / "caller-supplied"
    given.mkdir()

    suite_conftest.remove_own_run(None, failed=0)

    assert given.is_dir()
