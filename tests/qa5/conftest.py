"""Bring-up (env-plan §4, steps 1-11) and teardown (§9, steps 1-9), in one owner.

**One `controld` per process.** The registry, the stream ring and `compose._PLANE`
are module-global, so exactly one composition may exist at a time and scenarios
are serial. No `pytest-xdist` in this package.

**Readiness is two signals, not one.** There is no health or readiness endpoint
(B1); the closest proxy is `GET /api/fleet`, which needs a working store and can
fail for reasons unrelated to liveness. So bring-up gates on the `bound` event
`controld.start` sets — a real signal the product itself sets, and the only one
purely about liveness — **and** a functional probe. A probe failure after a
clean bind is `BLOCKED`, an environment verdict, never a product `FAIL`.

**Nothing here sleeps.** Every wait is a bounded predicate with a loud failure.

**Teardown verifies itself**, in the order the env plan fixes: the browser first
(a page holding an SSE connection keeps a server thread busy), then the readers,
then the server, then tmux, then the files. "Ran the cleanup" is not evidence.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
except ModuleNotFoundError as error:  # pragma: no cover - diagnosis, not control flow
    # **Loud, and explained.** `playwright` is not declared in `pyproject.toml`
    # while `testpaths = ["tests"]` collects this package, so a plain `pytest` on
    # a fresh checkout reaches this import and dies. Failing here is the RIGHT
    # direction — a machine without the browser must not report green — but a
    # bare `ModuleNotFoundError: playwright` tells the reader nothing about
    # whose problem it is. Declaring the dependency is a change to product
    # configuration, which this harness may not make; it is reported as a
    # blocker instead. `pyproject.toml:55-59` records that a marker declared
    # without a matching `addopts` deselection went unnoticed for three
    # milestones, which is why this is not "fixed" with a silent skip.
    raise ModuleNotFoundError(
        "tests/qa5 needs `playwright`, which pyproject.toml does not declare while "
        "testpaths=['tests'] collects this package. Install it "
        "(`pip install playwright && playwright install chromium`) or run without "
        "this package. Declaring the dependency is a product-configuration change "
        "this harness is not permitted to make; see TESTABILITY_BLOCKERS."
    ) from error

from shepherd.daemons import controld
from shepherd.core.runner import RunnerHandle
from shepherd.host.base import HostPlatform
from shepherd.host.detect import detect_host
from shepherd.store.db import Store, open_store
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION, read_schema_version
from shepherd.toolsurface.compose import RUNNER_SOCKET_KEY

from . import envredirect, runroot, tmuxctl
from .auditprobe import AuditProbe
from .constants import (
    CEILING_S,
    CONTROL_PANE,
    DESKTOP,
    PANES,
    PLANNED_SCENARIOS,
    QA_SOCKET,
    ROUND5_WIDTHS,
    SCENARIO_IN_TEST_NAME,
)
from .report import RunReport
from .rig import Rig
from .runroot import HarnessBlocked, RunRoot
from .seed import Seeded, seed_world
from .wire import Client, await_true

DB_NAME = "shepherd.db"

# ----- the run report, and the hooks that make it able to say FAIL ------------
#
# **A report that cannot express a failure is worse than no report.** Every
# `record()` call sits at the tail of a test body with a literal verdict, so a
# scenario that raised before reaching it simply vanished — measured across the
# 140 run files this harness had emitted: `FAIL` total 0, and 47 files all-green
# with `scenarios: 0`, each of which had gone on to overwrite `qa5-latest.json`.
# The two hooks below close both halves: `pytest_runtest_makereport` writes the
# row the aborted test could not, and `pytest_sessionfinish` refuses to publish a
# run whose record set is not the planned one.

_REPORT: RunReport | None = None
_ITEM_PHASES: dict[str, dict[str, Any]] = {}


def _report() -> RunReport:
    """The one report for this session, created on first use.

    Module-global rather than fixture-owned because the hooks need it for items
    whose fixtures never ran — which is precisely the case it exists to cover.
    """
    global _REPORT
    if _REPORT is None:
        _REPORT = RunReport(started_at=datetime.now(timezone.utc).isoformat())
    return _REPORT


def _scenario_id(item: pytest.Item) -> str:
    """`test_s13_...` -> `S13`. Anything else is a harness-level test, and is
    recorded under its own node name so it cannot be mistaken for a scenario —
    and so it lands in `extra` and refuses publication."""
    match = SCENARIO_IN_TEST_NAME.match(item.name)
    return f"S{int(match.group(1))}" if match else f"HARNESS:{item.name}"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "pure: exercises this harness's own guards and needs no environment "
        "(no run root, no daemon, no browser, no tmux server)",
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    """Write the row a test that died could not write for itself.

    Runs for all three phases and decides at `teardown`, which is the last one:
    a scenario can record PASS at the tail of its body and then fail in teardown,
    and a PASS row contradicted by a red test is exactly the lie this hook is
    here to stop — so that row is **overridden**, not left standing beside it.
    """
    phase_report = yield
    phases = _ITEM_PHASES.setdefault(item.nodeid, {})
    phases[phase_report.when] = phase_report
    if phase_report.when == "teardown":
        try:
            _account_for(item, phases)
        finally:
            _ITEM_PHASES.pop(item.nodeid, None)
    return phase_report


def _account_for(item: pytest.Item, phases: dict[str, Any]) -> None:
    report = _report()
    scenario = _scenario_id(item)
    failed = [name for name, rep in phases.items() if rep.failed]
    skipped = [name for name, rep in phases.items() if rep.skipped]
    if not failed and not skipped:
        return

    # 2000 characters, not 400: the whole point of this row is that somebody can
    # read what went wrong without re-running, and a playwright timeout's useful
    # part — which `wait_for_*` call, with what argument — is above the last 400.
    detail = "; ".join(f"{name}: {str(phases[name].longrepr)[-2000:]}" for name in failed + skipped)
    # `BLOCKED` is a distinct outcome and never rounds to either neighbour. A
    # `HarnessBlocked` — and a `pytest.skip` raised from a measured premise, which
    # is how wave 3 expresses BLOCKED — says the environment or the fixture was
    # wrong, not that the product failed.
    blocked = bool(skipped) or any("HarnessBlocked" in str(phases[name].longrepr) for name in failed)
    verdict = "BLOCKED" if blocked else "FAIL"

    existing = [row for row in report.scenarios if row.scenario == scenario]
    if existing:
        row = existing[-1]
        row.detail["overridden_by_harness"] = (
            f"the scenario recorded {row.verdict!r} and then the test ended "
            f"non-passing in {failed + skipped}; the verdict below is the test's"
        )
        row.detail["harness_failure"] = detail
        row.verdict = verdict
        report.lose(
            f"{scenario}: recorded a verdict and then ended {verdict} in "
            f"{failed + skipped} — the record has been overridden."
        )
        return

    report.record(
        scenario,
        "unknown",
        verdict,
        f"{item.name} was expected to run to its own record() call and state a verdict",
        f"it ended {verdict} in phase(s) {failed + skipped} without recording: {detail}",
        wrote_no_record_of_its_own=True,
        node_id=item.nodeid,
    )
    report.lose(
        f"{scenario}: ended {verdict} before recording its own evidence "
        f"(phases {failed + skipped}). Row written by the harness."
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Emit once, and publish **only** a run that accounted for every scenario.

    The completeness check is computed before the emit so the file carries its
    own verdict on itself, and `qa5-latest.json` is left untouched when it does
    not hold: a partial run that overwrites `latest` turns an aborted suite into
    the record of record.
    """
    report = _REPORT
    if report is None:
        return  # this package was never collected; nothing to say
    if not report.finished_at:
        report.finished_at = datetime.now(timezone.utc).isoformat()

    recorded = [row.scenario for row in report.scenarios]
    missing = [name for name in PLANNED_SCENARIOS if name not in recorded]
    extra = sorted(set(recorded) - set(PLANNED_SCENARIOS))
    duplicated = sorted({name for name in recorded if recorded.count(name) > 1})
    complete = not (missing or extra or duplicated)
    report.measure(
        "record_set",
        {
            "planned": len(PLANNED_SCENARIOS),
            "recorded": len(recorded),
            "missing": missing,
            "extra": extra,
            "duplicated": duplicated,
            "complete": complete,
            "pytest_exitstatus": int(exitstatus),
        },
    )
    if not complete:
        report.lose(
            f"the record set is not the planned one, so this run was NOT published "
            f"as qa5-latest.json: missing={missing}; extra={extra}; "
            f"duplicated={duplicated}"
        )

    path = report.emit()
    published = report.publish_latest(path) if complete else None

    writer = session.config.pluginmanager.get_plugin("terminalreporter")
    lines = [
        f"qa5 report: {path}",
        f"qa5 counts: {report.counts()}",
        (
            f"qa5 latest: published -> {published}"
            if complete
            else f"qa5 latest: REFUSED (missing={missing}; extra={extra}; "
            f"duplicated={duplicated}) — qa5-latest.json left untouched"
        ),
    ]
    for line in lines:
        if writer is not None:
            writer.write_line(line)
        else:  # pragma: no cover - only when -p no:terminal
            print(line)



def navigate(page: Page, target: str) -> None:
    """Click a nav entry — **through the drawer when the rail is off-canvas**.

    Below the drawer breakpoint the six nav entries sit at `x: -244..0` by
    design, and playwright refuses to click an element outside the viewport. A
    harness that clicked blindly would fail at every phone width and report it
    as a product fault; one that used `force=True` would be asserting that a
    control a person cannot reach is reachable.

    **The retry is for the drawer's own animation, not for flake.** The drawer
    closes on a nav click, so a check-then-click sequence can observe it open and
    click after it has begun sliding away. Each attempt re-reads the geometry and
    re-opens the drawer if it has to; three attempts is a bound, and blowing it
    raises rather than proceeding against a page that never navigated.
    """
    selector = f'.nav-item[data-page="{target}"]'
    off_screen = (
        "el => { const r = el.getBoundingClientRect();"
        " return r.right <= 0 || r.left >= window.innerWidth"
        " || r.bottom <= 0 || r.top >= window.innerHeight; }"
    )
    last: Exception | None = None
    for _ in range(3):
        opened_drawer = False
        if page.eval_on_selector(selector, off_screen):
            page.click("#drawer-open")
            page.wait_for_function(
                "(sel) => { const el = document.querySelector(sel);"
                " const r = el.getBoundingClientRect();"
                " return r.right > 0 && r.left < window.innerWidth"
                " && r.bottom > 0 && r.top < window.innerHeight; }",
                arg=selector,
            )
            opened_drawer = True
        try:
            page.click(selector, timeout=3000)
        except Exception as error:  # noqa: BLE001 - re-raised below if every attempt fails
            last = error
            continue
        page.wait_for_function(
            "(id) => { const el = document.getElementById(id);"
            " return el !== null && getComputedStyle(el).display !== 'none'; }",
            arg=f"page-{target}",
        )
        if opened_drawer:
            # **The page closes the drawer itself on a nav click** — `showPage`
            # removes `data-drawer` (measured: `data-drawer` is `null` and the
            # rail is back at `left: -244` immediately after the click). An
            # earlier version of this helper clicked `#drawer-open` again to
            # "tidy up" and so **re-opened** it, leaving a fixed rail on top of
            # the page it had just navigated to. Nothing to do here but check.
            page.wait_for_function(
                "(sel) => { const el = document.querySelector(sel);"
                " const r = el.getBoundingClientRect();"
                " return r.right <= 0 || r.left >= window.innerWidth; }",
                arg=selector,
            )
        return
    raise AssertionError(f"could not reach the {target} nav entry in three attempts: {last!r}")


def press_until_open(
    page: Page,
    dialog: str,
    press: Any,
    label: str,
    *,
    attempts: int = 3,
    per_attempt_ms: int = 4000,
) -> int:
    """Press until `#<dialog>` is open. Bounded, loud, and it says how many.

    **A retry against a MEASURED re-render, not a widened timeout.** The detail
    pane is rebuilt with `replaceChildren()` inside a `loadDetail()` that
    `projects.js:252-256` starts and never awaits, so for a frame the pane holds
    no `#proj-edit` at all. A press whose coordinates were read a moment earlier
    lands in that window, hits nothing, and the dialog never opens — which is
    what failed S19 and S33, at a different site each run, at roughly one
    full-suite run in five even behind a `networkidle` settle.

    A bound widened to cover this would stop being a bound, and it would hide the
    product defect rather than accommodate it. So: each attempt re-reads the
    control and presses again, three attempts is the bound, blowing it raises,
    and the **number of presses is returned** so a run that needed a retry says
    so in its report instead of looking identical to one that did not. It is the
    same shape as `navigate()`'s retry for the drawer animation.

    The dialog is checked *before* each press, so a press that did register is
    never followed by a second one — `showModal()` on an open dialog throws.
    """
    for index in range(attempts):
        if page.eval_on_selector(f"#{dialog}", "el => el.open") is True:
            return index
        press()
        try:
            page.wait_for_function(
                "(id) => document.getElementById(id).open === true",
                arg=dialog,
                timeout=per_attempt_ms,
            )
        except Exception:  # noqa: BLE001 - bounded, re-raised below if every attempt fails
            continue
        return index + 1
    raise AssertionError(
        f"{label}: #{dialog} did not open after {attempts} presses of its opener. "
        f"That is past the point where the unawaited loadDetail() race explains it."
    )


class Console:
    """`console.error` and `pageerror`, collected from before the first paint.

    Registered **before** navigation, because a listener added afterwards cannot
    see the errors a first paint produced — which is most of them.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.messages: list[str] = []

    def watch(self, page: Page) -> None:
        page.on(
            "console",
            lambda message: (
                self.messages.append(f"console.{message.type}: {message.text}")
                if message.type == "error"
                else None
            ),
        )
        page.on("pageerror", lambda error: self.messages.append(f"pageerror: {error}"))

    #: Chromium emits one of these for **every** refused or failed fetch, from
    #: the network stack rather than from any page code. It is not a
    #: `console.error(...)` call and not a `pageerror`, and no amount of correct
    #: handling suppresses it. Only S29 — which stops the daemon on purpose —
    #: may allow it, and it says so at the call site.
    NETWORK_NOISE = "Failed to load resource:"

    def assert_clean(self, context: str = "", allow_network: bool = False) -> None:
        messages = self.messages
        if allow_network:
            messages = [item for item in messages if self.NETWORK_NOISE not in item]
        assert messages == [], f"{context} [{self.label}] console/page errors: {messages}"


@dataclass
class Harness:
    """Everything a scenario is handed. One object, so nothing is re-derived."""

    run: RunRoot
    host: HostPlatform
    started: controld.Controld
    store: Store
    client: Client
    rig: Rig
    seeded: Seeded
    audit: AuditProbe
    playwright: Playwright
    browser: Browser
    report: RunReport
    controld_stopped: bool = False
    contexts: list[BrowserContext] = field(default_factory=list)
    bindings: dict[str, Any] = field(default_factory=dict)

    # ----- browser ----------------------------------------------------------
    def context(self, width: str = DESKTOP, **options: Any) -> BrowserContext:
        size = ROUND5_WIDTHS[width]
        context = self.browser.new_context(
            viewport={"width": size[0], "height": size[1]}, **options
        )
        context.set_default_timeout(CEILING_S * 1000)
        self.contexts.append(context)
        return context

    def page(self, width: str = DESKTOP, label: str = "page", **options: Any) -> tuple[Page, Console]:
        """A page with its console watcher armed **before** the first navigation."""
        context = self.context(width, **options)
        page = context.new_page()
        console = Console(label)
        console.watch(page)
        return page, console

    def open(
        self, nav: str | None = None, width: str = DESKTOP, label: str = "page", **options: Any
    ) -> tuple[Page, Console]:
        page, console = self.page(width=width, label=label, **options)
        page.goto(f"{self.client.origin}/")
        page.wait_for_function("() => document.readyState === 'complete'")
        if nav is not None:
            navigate(page, nav)
        return page, console

    def nav(self, page: Page, target: str) -> None:
        """Navigate, opening the drawer first when the nav is off-canvas."""
        navigate(page, target)

    def shots_dir(self) -> Path:
        return self.run.sub("shots")


@pytest.fixture(autouse=True)
def _close_this_scenarios_contexts(request: pytest.FixtureRequest) -> Iterator[None]:
    """Every scenario owns its browser contexts and gives them back.

    **`harness` is requested lazily**, so a `pure` test — one that exercises this
    harness's own guards and touches no service — does not drag the whole
    environment up behind it. Declaring `harness` as a parameter would force
    bring-up for every test in the package, including the ones whose entire
    point is that they need nothing.

    **This is a correctness fixture, not tidiness.** Without it the contexts
    accumulate for the whole run — by wave 6 there were around thirty, each
    holding an open SSE connection and its own renderer — and the browser slowed
    enough that a 10 s bounded wait in S33 began to expire on a healthy page,
    about one full-suite run in two while the same scenario passed 3/3 in
    isolation. The fix is to stop leaking them, not to widen the bound: a bound
    widened to cover a leak stops being a bound.

    Contexts the scenario closed itself are a non-event; anything that refuses
    to close is raised, because a browser handle this run cannot free is exactly
    what teardown's own check exists to catch.
    """
    if request.node.get_closest_marker("pure") is not None:
        yield
        return
    harness: Harness = request.getfixturevalue("harness")
    before = len(harness.contexts)
    try:
        yield
    finally:
        mine, harness.contexts[before:] = harness.contexts[before:], []
        refused = []
        for context in mine:
            try:
                context.close()
            except Exception as error:  # noqa: BLE001 - classified, never discarded
                if "closed" not in str(error).lower():
                    refused.append(repr(error))
        if refused:
            raise HarnessBlocked(f"a scenario's browser context would not close: {refused}")


# ----- bring-up ---------------------------------------------------------------
def _session_scratch() -> Path:
    """The long-lived, SHARED session directory. Never removed by this run."""
    configured = os.environ.get("QA5_SESSION_SCRATCH")
    if configured:
        return Path(configured)
    return Path("/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad")


def _open_store_and_set_the_knob(host: HostPlatform) -> None:
    """§4 step 4 — and the knob is set **before** `controld.start`.

    `compose.build_runner` reads `app_state["runner_socket"]` **once, at
    composition time**, and hands `permitted_sockets(socket)` to the exec site.
    Setting it afterwards changes nothing, which is why `killable` was empty in
    every prior round's fixture and why no kill this project ever drove could
    land on a real pane.
    """
    db_path = host.dirs().data_dir / DB_NAME
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = open_store(db_path)
    try:
        store.set_app_state(RUNNER_SOCKET_KEY, QA_SOCKET)
        workspaces = store.list_workspaces()
        if len(workspaces) != 1 or workspaces[0].id != "unassigned":
            raise HarnessBlocked(
                f"a freshly migrated database must hold exactly the reserved workspace; "
                f"found {[row.id for row in workspaces]}"
            )
    finally:
        store.close()


def _fixture_side_controls(store: Store, seeded: Seeded) -> list[str]:
    """§3c — the product is not the only thing that can be wrong.

    S11 is the first kill this project has ever driven against a real pane. Without
    these three controls a red S11 cannot be told apart from a wrongly seeded
    handle, and the second is far likelier on ground this new. A red here is
    `BLOCKED`; it says the *seed* was wrong, not that the shipped kill is.
    """
    evidence: list[str] = []

    # (1) pane-kill mechanics, fixture-side, using no product code.
    tmuxctl.new_session(CONTROL_PANE)
    if CONTROL_PANE not in tmuxctl.sessions():
        raise HarnessBlocked(f"{CONTROL_PANE} was not listed after new-session")
    tmuxctl.kill_session(CONTROL_PANE, tolerate_missing=False)
    if CONTROL_PANE in tmuxctl.sessions():
        raise HarnessBlocked(f"{CONTROL_PANE} survived its own kill-session")
    evidence.append("pane-kill mechanics: created, listed, killed, not listed")

    # (2) the seeded handles really round-trip through the store.
    for label in ("S-own-1", "S-own-2", "S-own-3", "S-own-4"):
        session = store.get_session(seeded.session(label))
        if session is None or session.runner_handle is None:
            raise HarnessBlocked(f"{label} has no runner_handle after seeding")
        handle = session.runner_handle
        # The round trip is through the **stored form**, which is the one
        # `runner/local.py` consumes: a three-field, separator-joined string.
        # Asserting the dataclass alone would not notice a store that wrote a
        # shape `from_text` cannot parse back.
        text = handle.to_text()
        if RunnerHandle.from_text(text) != handle:
            raise HarnessBlocked(f"{label}'s handle does not round-trip through its text: {text!r}")
        if handle.runner != "local" or handle.socket != QA_SOCKET:
            raise HarnessBlocked(f"{label}'s handle is not ours: {text!r}")
        if handle.session_name not in PANES:
            raise HarnessBlocked(f"{label}'s handle names an unknown pane: {text!r}")
        evidence.append(f"{label} -> {text}")
    evidence.append("handle round-trip: four owned sessions, three-field form, known panes")

    # (3) the socket knob, read back AFTER `controld.start`.
    stored = store.get_app_state(RUNNER_SOCKET_KEY)
    if stored != QA_SOCKET:
        raise HarnessBlocked(f"runner_socket reads back {stored!r}, not {QA_SOCKET!r}")
    evidence.append(f"socket knob: runner_socket == {QA_SOCKET!r} after controld.start")
    return evidence


def _sweep_panes() -> str:
    """Destroy any session left on **our** socket by an earlier run, by name.

    §4 step 5 used to create the four panes against whatever was already there.
    A run that died between `new-session` and teardown leaves `shepherd_r5a`
    alive, `new-session -s shepherd_r5a` then exits non-zero, and the harness
    bricks itself until somebody kills the panes by hand — directories are swept
    at mint, sessions never were.

    **By name, then asserted empty.** The socket is this harness's alone, so a
    survivor under any other name is a fact about the machine that must stop the
    run rather than be tidied away: nothing else is entitled to be here, and
    deleting an entry we did not name is the rule `runroot.sweep` exists to keep.
    """
    before = tmuxctl.sessions()
    for pane in (*PANES, CONTROL_PANE):
        tmuxctl.kill_session(pane)
    remaining = tmuxctl.sessions()
    if remaining:
        raise HarnessBlocked(
            f"sessions this harness did not name remain on {QA_SOCKET} after sweeping "
            f"its own: {remaining}. Stop; do not delete them."
        )
    return f"swept {before} from {QA_SOCKET}" if before else f"{QA_SOCKET} was already empty"


@pytest.fixture(scope="session")
def harness() -> Iterator[Harness]:
    """§4 steps 1-11, **every one of them inside the `try` that owns teardown**.

    Steps 1-5 used to run above the `try`. A failure in any of them — a run root
    that would not mint, a tmux server that would not start, a fourth pane that
    would not come up — leaked the run root, `/tmp/shq5-<pid>` and every pane
    already created. The next run swept the directories and inherited the panes.
    """
    report = _report()
    pid = os.getpid()
    run: RunRoot | None = None

    started: controld.Controld | None = None
    playwright: Playwright | None = None
    browser: Browser | None = None
    rig: Rig | None = None
    harness_object: Harness | None = None
    try:
        # --- step 1-2: the run root and the short runtime dir ---------------
        run = runroot.mint(_session_scratch(), pid)
        report.measure("run_root", str(run.root))
        report.measure("runtime_dir", str(run.runtime_dir))
        report.measure("socket_bytes_spent", runroot.assert_socket_budget(run.runtime_dir))
        report.measure("tmux_version", tmuxctl.version())

        with envredirect.redirected(run) as rows:
            report.measure("environment", {k: v for k, v in rows.items()})
            host = detect_host()
            report.measure("data_dir", str(host.dirs().data_dir))

            # --- step 4: the store, and the knob, BEFORE controld.start -----
            _open_store_and_set_the_knob(host)

            # --- step 5: the tmux server and the four owned panes -----------
            report.measure("pane_sweep", _sweep_panes())
            for pane in PANES:
                tmuxctl.new_session(pane)
            await_true(
                lambda: set(PANES) <= set(tmuxctl.sessions()),
                f"the four panes were never all listed on {QA_SOCKET}",
                CEILING_S,
            )

            # --- step 6: start controld. The call returns only once bound. --
            started = controld.start(
                host=host, port=0, engine_config_dir=run.sub("engine-config")
            )
            if started.port == 0:
                raise HarnessBlocked("controld returned port 0")
            if not started.control_socket_path.exists():
                raise HarnessBlocked(f"the control socket is absent: {started.control_socket_path}")
            store = started.store
            version = read_schema_version(host.dirs().data_dir / DB_NAME)
            if version != EXPECTED_SCHEMA_VERSION:
                raise HarnessBlocked(
                    f"the store migrated to schema {version}, not {EXPECTED_SCHEMA_VERSION}"
                )
            report.measure("schema_version", version)
            client = Client(started.port)

            # --- step 7: the functional readiness probe ---------------------
            def fleet_answers() -> bool:
                try:
                    response = client.get("/api/fleet")
                except OSError:
                    return False
                return response.status == 200 and response.json().get("ok") is True

            await_true(fleet_answers, "GET /api/fleet never answered 200 {ok:true}", CEILING_S)

            # --- step 8: seed the world -------------------------------------
            seeded = seed_world(client, store, run.sub("work"), run.sub("repo"))

            # --- step 9: chromium -------------------------------------------
            playwright = sync_playwright().start()
            executable = Path(playwright.chromium.executable_path)
            if not executable.exists():
                raise HarnessBlocked(f"chromium's executable_path does not exist: {executable}")
            browser = playwright.chromium.launch(headless=True)
            report.measure("chromium", executable.as_posix())

            # --- step 10: the rig, proved live, and the §3c controls --------
            rig = Rig(client, started.port)
            probe = rig.control("RIG-PROBE")
            probe.assert_empty("the rig's own probe window must be empty at bring-up")
            report.measure("rig_probe", {name: len(frames) for name, frames in probe.control.items()})
            report.measure("fixture_side_controls", _fixture_side_controls(store, seeded))

            harness_object = Harness(
                run=run,
                host=host,
                started=started,
                store=store,
                client=client,
                rig=rig,
                seeded=seeded,
                audit=AuditProbe.for_host(host),
                playwright=playwright,
                browser=browser,
                report=report,
            )
            yield harness_object
    finally:
        # **The report is not emitted here.** A row written by
        # `pytest_runtest_makereport` for the last item's teardown phase lands
        # after this finally runs, and a file written before the last row is a
        # file that can be missing exactly the failure it exists to carry.
        # `pytest_sessionfinish` emits, once, at the end.
        teardown = _teardown(harness_object, started, browser, playwright, rig, run, report)
        report.teardown = teardown
        report.finished_at = datetime.now(timezone.utc).isoformat()


def _teardown(
    harness_object: Harness | None,
    started: controld.Controld | None,
    browser: Browser | None,
    playwright: Playwright | None,
    rig: Rig | None,
    run: RunRoot | None,
    report: RunReport,
) -> list[str]:
    """§9 steps 1-9. Every step checks its own result; none swallows an error.

    Failures are **collected**, not suppressed: a teardown that stops at its
    first problem leaks whatever the later steps would have freed, and a
    teardown that ignores its own exit code leaks silently. At the end the
    collection is raised.
    """
    lines: list[str] = []
    problems: list[str] = []

    def step(name: str, action: Any) -> None:
        try:
            result = action()
        except Exception as error:  # noqa: BLE001 - collected and re-raised below
            problems.append(f"{name}: {error!r}")
        else:
            lines.append(f"{name}: {result if result is not None else 'ok'}")

    # 1-2: pages and contexts, then the browser — by handle, never `pkill`,
    # and never a signal to 0, 1 or -1.
    if harness_object is not None:
        step("close contexts", lambda: _close_contexts(harness_object))
    if browser is not None:
        step("close chromium", lambda: (browser.close(), browser.is_connected())[1] is False)
    if playwright is not None:
        step("stop playwright", playwright.stop)

    # 3: the SSE readers.
    if rig is not None:
        step("close SSE readers", rig.close)

    # 4: controld — **conditionally**. S29 stops the daemon as its own `When`,
    # and `controld.stop` must not be called twice. Which branch ran is recorded,
    # because "teardown skipped the stop" and "teardown never reached the stop"
    # are different facts.
    if started is not None:
        already = harness_object is not None and harness_object.controld_stopped
        if already:
            step("controld", lambda: _assert_sockets_gone(started, "already stopped by S29"))
        else:
            step("controld", lambda: _stop_controld(started))
        report.measure("teardown_controld_branch", "skipped (S29)" if already else "stopped here")

    # 5-6: the panes, by name, then the socket asserted empty. No kill-server.
    step("kill panes", _kill_panes)
    step("socket empty", _assert_socket_empty)

    # 7-9: the files, and the repo. `run` is None only when step 1 itself failed,
    # in which case there is nothing minted to destroy — and saying which of the
    # two happened is the point of recording the branch rather than skipping
    # silently.
    if run is None:
        lines.append("files: nothing minted (bring-up failed at step 1)")
    else:
        step("files", lambda: runroot.destroy(run))

    if problems:
        # **The lines are attached BEFORE the raise.** They used to be assigned
        # by the caller from this function's return value, so a teardown that
        # refused threw its own evidence away — and the run where teardown fails
        # is the one where knowing which steps ran matters most. Measured: a
        # probe that left a stranger on the socket produced `teardown: []`
        # while three of the steps had in fact completed.
        report.teardown = [*lines, *(f"PROBLEM {problem}" for problem in problems)]
        raise HarnessBlocked("teardown did not verify: " + "; ".join(problems))
    return lines


def _close_contexts(harness_object: Harness) -> str:
    """Close every context, and **say** which ones would not close.

    A `continue` here would be catch-and-continue in teardown — the shape that
    turns a broken environment into a green run. A context a scenario already
    closed raises on a second close and is a non-event; anything else is a
    browser handle this run could not free, and the count of each goes into the
    teardown line rather than into the void.
    """
    closed, already, refused = 0, 0, []
    for context in harness_object.contexts:
        try:
            context.close()
        except Exception as error:  # noqa: BLE001 - classified, never discarded
            if "closed" in str(error).lower():
                already += 1
            else:
                refused.append(repr(error))
            continue
        closed += 1
    if refused:
        raise HarnessBlocked(f"{len(refused)} browser context(s) would not close: {refused}")
    return f"{closed} closed, {already} already closed by their scenario"


def _stop_controld(started: controld.Controld) -> str:
    outcome = controld.stop(started)
    hung = getattr(outcome, "hung", ()) or getattr(outcome, "hung_threads", ())
    if hung:
        raise HarnessBlocked(f"shutdown reported hung threads: {hung!r}")
    return _assert_sockets_gone(started, "stopped here")


def _assert_sockets_gone(started: controld.Controld, branch: str) -> str:
    if started.control_socket_path.exists():
        raise HarnessBlocked(f"the control socket survived shutdown: {started.control_socket_path}")
    return f"{branch}; control socket unlinked"


def _kill_panes() -> str:
    """By name, one by one. "session not found" is the **expected** answer for
    `shepherd_r5a`, which the product destroyed inside S11, and for
    `shepherd_r5c`, which the fixture destroyed inside S17."""
    outcomes: list[str] = []
    for pane in (*PANES, CONTROL_PANE):
        result = tmuxctl.kill_session(pane)
        outcomes.append(f"{pane}={'gone' if result.returncode != 0 else 'killed'}")
    return ", ".join(outcomes)


def _assert_socket_empty() -> str:
    """The assertion that replaces a `kill-server` step.

    It proves the same property and cannot be copied into a context where the
    `-L` is missing — which is what made the 2026-09-12 verb dangerous.
    """
    remaining = tmuxctl.sessions()
    if remaining:
        raise HarnessBlocked(f"sessions remain on {QA_SOCKET}: {remaining}")
    return f"no session remains on {QA_SOCKET}"
