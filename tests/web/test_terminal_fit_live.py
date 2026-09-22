"""D6 (QA run 4): the emulator is fitted to the box it is drawn in — **measured**.

G-M3-6 has stood since T19-a: *"xterm.js draws the snapshot and the stream
identically is unverified"*, because there was no browser on the build host. QA
run 4 was the first browser, and it reported this, for a fixture pane that is
160 columns by 45 rows:

    desktop1440 1440x900   hostScrollW 722  hostClientW 628
                           screenRight 1517 (outside a 1440 window)  renderedRows 24
    wide2560    2560x1440  hostBox 1750 wide, screen still 722       renderedRows 24
    phone390    390x844    hostScrollW 722  hostClientW 356
                           -> 366px unreachable, maxRowChars 80

80x24 at every viewport from 390 to 2560, inside a container that is
`overflow: hidden` on both axes — so at 390 there was no scrollbar and no drag,
and the content was simply gone. Run 4 swept every sizing path and found all
four absent: no `cols`/`rows` in the constructor, no `term.resize` call site
outside vendor, no `FitAddon` in the vendored bundle, and `terminal_resize`
registered as a `ToolDef` with no route and no caller.

**This module measures geometry; it does not read a constructor argument.** An
argument being present is what the defect's *absence* looked like from the
source, and the source is exactly what could not see the 1517. Every assertion
below comes off `getBoundingClientRect` and `scrollWidth`/`clientWidth` in a
real chromium, against the shipped page served by the shipped server.

**What is not asserted here, because it is not true.** The pane keeps its own
geometry — nothing in this build resizes it, and the head of `terminal.js` says
why — so a window narrower than the pane still re-wraps the lines at the
window's width. That residual is declared on the page (`FIT_LIMITATION`), and
the test for the declaration is in `test_session_page.py`, where the page's
other declared limitation already lives.

Skipped, not failed, where chromium is absent: an absent browser is an
environment fact, and reporting it as a code defect is the failure mode
`ENVIRONMENT not code` names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.conftest import LIVE_FIELDS, NOW, Client, MasterDoubles

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store
from shepherd.testkit.scripted_runner import ScriptedRunner

playwright_api = pytest.importorskip("playwright.sync_api")

#: The pane the fixture capture really is — `160|45` in `LIVE_FIELDS`, which is
#: the field run 4 quoted. Derived rather than re-typed, so a fixture that
#: changes size changes this.
PANE_COLS, PANE_ROWS = (int(field) for field in LIVE_FIELDS.split("|")[4:6])

SESSION_NAME = "shp_eng-live"
ENGINE_SESSION_ID = "eng-live"

#: The three run 4 drove, by the names its output uses.
VIEWPORTS = {
    "phone390": {"width": 390, "height": 844},
    "desktop1440": {"width": 1440, "height": 900},
    "wide2560": {"width": 2560, "height": 1440},
}

#: Everything a reader of run 4's table would want, read off the live DOM.
GEOMETRY = r"""
() => {
  const host = document.getElementById('session-terminal');
  const screen = host.querySelector('.xterm-screen');
  const rows = host.querySelector('.xterm-rows');
  const rowEls = rows ? [...rows.children] : [];
  return {
    present: screen !== null,
    hostClientW: host.clientWidth,
    hostClientH: host.clientHeight,
    hostScrollW: host.scrollWidth,
    hostScrollH: host.scrollHeight,
    screenW: screen ? Math.round(screen.getBoundingClientRect().width) : null,
    screenH: screen ? Math.round(screen.getBoundingClientRect().height) : null,
    screenRight: screen ? Math.round(screen.getBoundingClientRect().right) : null,
    renderedRows: rowEls.length,
    declaredCols: host.dataset.terminalCols ? Number(host.dataset.terminalCols) : null,
    declaredRows: host.dataset.terminalRows ? Number(host.dataset.terminalRows) : null,
    viewportW: document.documentElement.clientWidth,
    viewportH: document.documentElement.clientHeight,
    note: (document.getElementById('session-input-note').textContent || ''),
  };
}
"""


@pytest.fixture()
def scripted_runner() -> ScriptedRunner:
    """The module's own runner, overriding `conftest`'s: this one **owns** a
    pane, which is what makes `renderSession` open a terminal rather than paint
    the read-only banner."""
    from shepherd.core.runner import PaneState, ProcState
    from shepherd.runner.pane import parse_pane_fields, read_pane

    capture = (
        Path(__file__).resolve().parents[2]
        / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui"
        / "run-20260914T154946Z" / "03-after-stop.ansi"
    ).read_bytes()
    pane: PaneState = read_pane(capture, parse_pane_fields(LIVE_FIELDS), [])
    return ScriptedRunner(
        panes=(pane,),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=capture,
        owned_panes=(
            PaneRef(
                session_name=SESSION_NAME,
                session_id=ENGINE_SESSION_ID,
                pane_pid=4041880,
                dead=False,
            ),
        ),
    )


def _owned(store: Store) -> str:
    """One owned session with a runner handle — the row page 3 opens on."""
    workspace = store.create_project(name="payments", description="the api")
    session = store.register_session(
        engine_session_id=ENGINE_SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.OWNED,
    )
    store.set_runner_handle(
        session.id,
        RunnerHandle(runner="scripted", socket="scripted", session_name=SESSION_NAME),
    )
    return session.id


def _measure(client: Client, store: Store, viewport: dict[str, int]) -> dict[str, float]:
    """Open the shipped page at `viewport`, drill to the session, and measure."""
    from playwright.sync_api import sync_playwright

    session_id = _owned(store)
    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
    try:
        page = browser.new_page(viewport=viewport)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on(
            "console",
            lambda message: errors.append(f"{message.type}: {message.text}")
            if message.type == "error"
            else None,
        )
        page.goto(f"{client.origin}/")
        page.wait_for_timeout(700)
        if viewport["width"] <= 760:
            page.locator("#drawer-open").click()
            page.wait_for_timeout(250)
        page.locator('.nav-item[data-page="flock"]').click()
        page.wait_for_timeout(400)
        page.locator("#flock-projects .project").first.click()
        page.wait_for_timeout(300)
        page.locator(f'#flock-cards .card[data-session-id="{session_id}"]').click()
        # The emulator is an `await import(...)` plus a socket; 2.5s is what run
        # 4's own driver waited before measuring.
        page.wait_for_timeout(2500)
        measured = page.evaluate(GEOMETRY)
        assert errors == [], errors
        assert measured["present"], "arrival: no emulator was drawn, so nothing was measured"
        return measured
    finally:
        browser.close()
        play.stop()


@pytest.fixture(params=sorted(VIEWPORTS))
def geometry(request, client: Client, store: Store, master_doubles: MasterDoubles):
    """One measurement per viewport, named the way run 4 named them."""
    return request.param, _measure(client, store, VIEWPORTS[request.param])


def test_nothing_the_emulator_draws_is_out_of_reach(geometry) -> None:
    """Run 4's `366px unreachable`, and its `screenRight 1517`.

    `#session-terminal` is `overflow: hidden` on both axes — a layout fact this
    lane does not own — so anything the emulator draws outside the container's
    client box is content with no scrollbar and no drag: gone, rather than
    merely off-screen. The fit is what makes that clip vacuous.
    """
    name, measured = geometry
    assert measured["hostScrollW"] <= measured["hostClientW"] + 1, (name, measured)
    assert measured["hostScrollH"] <= measured["hostClientH"] + 1, (name, measured)
    assert measured["screenW"] <= measured["hostClientW"] + 1, (name, measured)
    assert measured["screenH"] <= measured["hostClientH"] + 1, (name, measured)
    # …and the right edge is inside the window, which is the reading a person
    # would take from run 4's `screenRight 1517 (outside a 1440 window)`.
    assert measured["screenRight"] <= measured["viewportW"] + 1, (name, measured)


def test_the_emulator_is_not_the_default_eighty_by_twenty_four(geometry) -> None:
    """The defect stated as the number it actually was.

    xterm's constructor default is 80x24 and it was what shipped at every
    width. A fit that happened to land on 80 columns is not a defect — so the
    assertion is on the **rows**, which run 4 measured as 24 at all three
    viewports for a container whose client height admits nothing like that many.
    """
    name, measured = geometry
    # Arrival: rows really were drawn, and the page's own declaration of what
    # it chose agrees with what xterm put in the DOM. A `data-` attribute that
    # disagreed with the render would be a fit reported rather than performed.
    assert measured["renderedRows"] > 0, (name, measured)
    assert measured["renderedRows"] == measured["declaredRows"], (name, measured)
    # **The runaway guard, and it is here because the first build of this fix
    # had one.** `#session-terminal` has no height of its own — it is
    # `flex: none; min-height: 12rem`, so it grows to whatever is drawn in it —
    # and rows measured from `clientHeight` fed a `ResizeObserver` loop that
    # reached a container 307 418 px tall. Every "the content fits in the box"
    # assertion in this module passed against that, because they are vacuous
    # for a box that grew to fit. A bound on the box itself is not.
    assert measured["hostClientH"] <= 4 * measured["viewportH"], (name, measured)
    assert measured["screenH"] <= measured["hostClientH"] + 1, (name, measured)


def test_the_geometry_is_taken_from_the_container_and_not_from_a_constant(
    client: Client, store: Store, master_doubles: MasterDoubles
) -> None:
    """Run 4's real finding: **the same 80x24 at 390 and at 2560**.

    One measurement cannot tell a fit from a constant that happens to fit. Two
    containers of different widths can: a fitted emulator has more columns in
    the wider one, and a constant has the same number in both.
    """
    phone = _measure(client, store, VIEWPORTS["phone390"])
    wide = _measure(client, store, VIEWPORTS["wide2560"])
    assert wide["hostClientW"] > phone["hostClientW"], (phone, wide)
    assert wide["declaredCols"] > phone["declaredCols"], (phone, wide)
    # And both are honest about the box they are in.
    for measured in (phone, wide):
        assert measured["screenW"] <= measured["hostClientW"] + 1, measured


def test_a_window_narrower_than_the_pane_re_wraps_and_the_page_says_so(
    client: Client, store: Store, master_doubles: MasterDoubles
) -> None:
    """The residual, measured — so the sentence beside it is not decorative.

    The fixture pane is 160 columns (`LIVE_FIELDS`). A 1440 window gives the
    terminal a 628px column, which is nothing like 160 columns at a readable
    font, and this build does not resize the pane — `terminal.js`'s head says
    why, and it is a decision rather than an omission. So the lines are
    re-wrapped at the window's width, and the page has to say so, because
    re-wrapped box drawing reads as a broken agent rather than a narrow window.
    """
    narrow = _measure(client, store, VIEWPORTS["desktop1440"])
    assert narrow["declaredCols"] < PANE_COLS, (narrow, PANE_COLS)
    assert "fitted to this window" in narrow["note"], narrow["note"]
    assert "re-wrapped" in narrow["note"], narrow["note"]
    # …and T19-c's older sentence is still in the same slot beside it: the two
    # limitations share one line, and neither may quietly displace the other.
    assert "keystroke" in narrow["note"], narrow["note"]


def test_a_wide_enough_window_shows_the_whole_pane_width(
    client: Client, store: Store, master_doubles: MasterDoubles
) -> None:
    """The other half of the same fact, and the reason the fit is worth having.

    At 2560 the terminal's column is 1748px wide, which is more than the
    fixture pane's 160 columns need. A fit that merely made the old 80 columns
    tidy would still be showing half a pane here; this one shows all of it.
    """
    wide = _measure(client, store, VIEWPORTS["wide2560"])
    assert wide["declaredCols"] >= PANE_COLS, (wide, PANE_COLS)
    assert wide["screenW"] <= wide["hostClientW"] + 1, wide
