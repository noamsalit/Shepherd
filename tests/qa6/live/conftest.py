"""The live lane's fail-closed host guard (INC-1; realclaude.py).

Every module in `tests/qa6/live/` runs a real engine with, under
`needs_real_home`, the user's real HOME. Before any fixture of a live module
starts anything, and around every live scenario, the user's
`~/.local/bin/claude` is compared against its state at run START
(`<run_dir>/claude-link-start.json`, written by the runner — or by
`bootstrap.mint` for a standalone or mutation run). It is never compared
against "healthy": at the time of writing it is dangling, and that is the
baseline, not a failure.

* changed before a module or a scenario → `Blocked(REPAIR_MESSAGE …)`, so the
  scenario is BLOCKED and nothing live runs;
* changed after a scenario → a teardown problem (blocks GREEN), and the
  runner's own post-lane check stops the run.

Reads only: lstat, readlink, realpath. Nothing here writes outside the run dir.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .. import paths, realclaude
from ..sandbox import RunContext
from ..verdict import Blocked


def _start_state(run: RunContext) -> dict[str, object]:
    start = realclaude.start_link_state(run.run_dir)
    if start is None:
        raise Blocked(f"no run-start record of {paths.REAL_CLAUDE_BIN} in {run.run_dir}: "
                      "a live scenario cannot tell whether the run changed it")
    return start


def _refuse_if_changed(run: RunContext, where: str) -> None:
    changed = realclaude.compare(_start_state(run), realclaude.link_state())
    if changed is not None:
        raise Blocked(f"{where}: {changed}")


@pytest.fixture(scope="module", autouse=True)
def claude_link_guard_module(request: pytest.FixtureRequest, qa6_run: RunContext) -> Iterator[None]:
    """Autouse at module scope: runs before the module's own fixtures start any instance."""
    _refuse_if_changed(qa6_run, f"before {request.node.nodeid}")
    yield
    changed = realclaude.compare(_start_state(qa6_run), realclaude.link_state())
    if changed is not None:
        qa6_run.teardown_problem(str(request.node.nodeid), changed)
        raise AssertionError(changed)


@pytest.fixture(autouse=True)
def claude_link_guard(request: pytest.FixtureRequest, qa6_run: RunContext) -> Iterator[None]:
    _refuse_if_changed(qa6_run, f"before {request.node.nodeid}")
    yield
    changed = realclaude.compare(_start_state(qa6_run), realclaude.link_state())
    if changed is not None:
        qa6_run.teardown_problem(str(request.node.nodeid), changed)
        raise AssertionError(changed)
