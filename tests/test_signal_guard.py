"""The runtime net from `conftest.py`, proved rather than promised.

Signal `0` delivers nothing — it is the "does this pid exist" probe — so these
assertions are safe to run even if the guard were absent. That is deliberate: a
test of a reboot-prevention guard must not be able to cause the reboot.
"""

from __future__ import annotations

import os
import subprocess

import pytest


@pytest.mark.parametrize("pid", [1, 0, -1])
def test_a_signal_that_could_reach_init_is_refused(pid: int) -> None:
    """P-M3-7's runtime half: init, the group, and the broadcast are all refused."""
    with pytest.raises(AssertionError, match="refused os.kill"):
        os.kill(pid, 0)


def test_killpg_to_the_group_is_refused_too() -> None:
    """`killpg` is the second idiom, and it reaches further than `kill`."""
    with pytest.raises(AssertionError, match="refused os.killpg"):
        os.killpg(0, 0)


def test_a_real_child_is_still_signalable() -> None:
    """The guard narrows nothing that a test legitimately does."""
    child = subprocess.Popen(["sleep", "30"])
    try:
        os.kill(child.pid, 0)  # exists, and the guard let it through
    finally:
        child.terminate()
        child.wait(timeout=5)
