"""qa6's pytest plumbing: verdict records, stop-ifs, and module-scoped fixtures.

**Import-inert** (B-10): importing this file starts nothing, reads no
environment and touches no file. The default lane collects `tests/qa6` and
deselects it by marker; everything here is a hook or a fixture that only acts
for items carrying the `qa6`/`qa6live` markers.

What it does for a qa6 run:

* refuses to run qa6 items when `pytest-randomly` is active (waves are ordered);
* turns each scenario test's outcome into exactly one record (`report.py`):
  PASS; `FAIL(assert)` for an AssertionError; `FAIL(bound)` for a
  `ProductFail`; `BLOCKED` for `Blocked`, a skip, or any setup error — a
  harness that could not set up has proven nothing about the product;
* applies the runner's stop-ifs: an id listed in `$QA6_BLOCKED_FILE` is
  BLOCKED at setup with the listed reason, and never runs;
* records every teardown error as a teardown problem (which blocks GREEN).

Fixtures: `qa6_run` (session: the `RunContext`), `rec` (function: the clause
`Recorder` for this scenario), `pool` (module: `InstancePool`, closed and
self-verified at module end), `browser_session` (module: Playwright per
module, never per session — W7.1).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator, Iterator
from pathlib import Path

import pytest

from typing import TYPE_CHECKING

from .verdict import Blocked, ProductFail, Recorder

if TYPE_CHECKING:
    from .browser import BrowserSession
    from .pool import InstancePool
    from .sandbox import RunContext

SCENARIO_MARK = "qa6_scenario"
QA6_MARKS = ("qa6", "qa6live")

_RECORDERS: dict[str, Recorder] = {}
_OUTCOMES: dict[str, dict[str, object]] = {}


def _is_qa6(item: pytest.Item) -> bool:
    return any(item.get_closest_marker(mark) is not None for mark in QA6_MARKS)


def scenario_id(item: pytest.Item) -> str | None:
    marker = item.get_closest_marker(SCENARIO_MARK)
    if marker is None or not marker.args:
        return None
    return str(marker.args[0])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    selected = [item for item in items if _is_qa6(item)]
    if not selected:
        return
    if config.pluginmanager.hasplugin("randomly"):
        raise pytest.UsageError(
            "qa6 waves are ordered: run with `-p no:randomly` (tests/qa6/run.py always does)"
        )


# ----- the run context ---------------------------------------------------------


@pytest.fixture(scope="session")
def qa6_run() -> Iterator[RunContext]:
    """The runner's `RunContext`, or a standalone one minted for this process."""
    from . import bootstrap
    from .sandbox import context_from_env

    run = context_from_env(os.environ)
    if run is not None:
        yield run
        return
    standalone = bootstrap.standalone_run()
    try:
        yield standalone
    finally:
        bootstrap.standalone_teardown(standalone)


@pytest.fixture
def rec(request: pytest.FixtureRequest) -> Recorder:
    sid = scenario_id(request.node) or request.node.name
    recorder = Recorder(scenario=sid)
    _RECORDERS[request.node.nodeid] = recorder
    return recorder


@pytest.fixture(scope="module")
def pool(request: pytest.FixtureRequest, qa6_run: RunContext) -> Iterator[InstancePool]:
    from .pool import InstancePool

    instances = InstancePool(qa6_run, owner=str(request.node.nodeid))
    yield instances
    problems = instances.close()
    if problems:
        raise AssertionError(f"module teardown problems: {problems}")


@pytest.fixture(scope="module")
def browser_session(request: pytest.FixtureRequest, qa6_run: RunContext) -> Iterator[BrowserSession]:
    from .browser import BrowserSession

    session = BrowserSession(qa6_run.run_dir / "ui")
    session.start()
    yield session
    problems = session.stop()
    for problem in problems:
        qa6_run.teardown_problem(str(request.node.nodeid), problem)
    if problems:
        raise AssertionError(f"browser teardown problems: {problems}")


# ----- stop-ifs ----------------------------------------------------------------


def _blocked_by_runner(sid: str) -> str | None:
    path = os.environ.get("QA6_BLOCKED_FILE")
    if not path or not Path(path).exists():
        return None
    decoded: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(decoded, dict):
        reason = decoded.get(sid)
        return str(reason) if reason is not None else None
    return None


def pytest_runtest_setup(item: pytest.Item) -> None:
    if not _is_qa6(item):
        return
    sid = scenario_id(item)
    if sid is None:
        return
    reason = _blocked_by_runner(sid)
    if reason is not None:
        raise Blocked(f"stop-if: {reason}")


# ----- outcome → record ----------------------------------------------------------


def _classify(excinfo: pytest.ExceptionInfo[BaseException] | None, when: str) -> tuple[str, str | None, str]:
    if excinfo is None:
        return "PASS", None, ""
    error = excinfo.value
    text = str(error)[:2000]
    if isinstance(error, Blocked):
        return "BLOCKED", None, error.reason[:2000]
    if excinfo.errisinstance(pytest.skip.Exception):
        return "BLOCKED", None, f"skipped: {text}"
    if when == "setup":
        return "BLOCKED", None, f"setup failed ({type(error).__name__}): {text}"
    if isinstance(error, ProductFail):
        return "FAIL", "bound", text
    if isinstance(error, AssertionError):
        return "FAIL", "assert", text
    return "FAIL", "assert", f"unexpected {type(error).__name__} in the scenario body: {text}"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if _is_qa6(item):
        _account(item, call, report)
    return report


def _account(item: pytest.Item, call: pytest.CallInfo[None], report: pytest.TestReport) -> None:
    sid = scenario_id(item)
    state = _OUTCOMES.setdefault(item.nodeid, {"verdict": None, "started": time.monotonic()})
    if call.when in ("setup", "call"):
        if state.get("verdict") is None or call.when == "call":
            if report.skipped and call.excinfo is not None and call.excinfo.errisinstance(pytest.skip.Exception):
                verdict, kind, reason = "BLOCKED", None, f"skipped: {call.excinfo.value}"
            else:
                verdict, kind, reason = _classify(call.excinfo, call.when)
            if call.when == "setup" and verdict == "PASS":
                return
            state.update(verdict=verdict, fail_kind=kind, reason=reason)
            recorder = _RECORDERS.get(item.nodeid)
            if verdict == "PASS" and recorder is not None and not recorder.finished and sid is not None:
                state.update(verdict="BLOCKED", fail_kind=None,
                             reason="harness: the scenario returned without calling rec.finish()")
    if call.when == "teardown":
        run_dir = os.environ.get("QA6_RUN_DIR")
        if call.excinfo is not None and run_dir:
            _teardown_problem(Path(run_dir), item.nodeid, str(call.excinfo.value)[:1000])
        if sid is not None and state.get("verdict") is not None:
            _write(item, sid, state)


def _teardown_problem(run_dir: Path, where: str, problem: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "teardown-problems.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"where": where, "problem": problem, "at": time.time()}) + "\n")


def _write(item: pytest.Item, sid: str, state: dict[str, object]) -> None:
    from .report import append_record, build_record, record_path

    recorder = _RECORDERS.get(item.nodeid)
    lane = os.environ.get("QA6_LANE", "adhoc")
    wave = os.environ.get("QA6_WAVE", "x")
    started = state.get("started")
    duration = time.monotonic() - started if isinstance(started, float) else 0.0
    kind = state.get("fail_kind")
    record = build_record(
        sid,
        verdict=str(state.get("verdict")),
        fail_kind=str(kind) if kind is not None else None,
        reason=str(state.get("reason") or ""),
        clauses=recorder.as_json() if recorder is not None else [],
        evidence=recorder.evidence if recorder is not None else [],
        node=item.nodeid,
        lane_process=f"{lane}-w{wave}",
        duration_s=duration,
    )
    run_dir = os.environ.get("QA6_RUN_DIR")
    target = Path(run_dir) if run_dir else Path(str(item.config.rootpath)) / ".qa6-adhoc"
    append_record(record_path(target, lane, wave), record)
