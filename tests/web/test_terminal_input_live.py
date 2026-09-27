"""P12 / D76 (ruling 18, SD-05): keys typed into the real emulator reach the pane.

Seam: a real chromium against the shipped page served by the shipped server
(the `client` fixture), with the scripted runner behind `invoke()`. The key
presses are the browser's own — `page.keyboard` into a focused xterm.js — and
what is asserted is what the runner was handed (`ScriptedRunner.writes`),
which is the far end of the whole path: emulator → `onData` → socket → the
server's reader → `TerminalStream.write` → `Runner.write`.

Skipped, not failed, where chromium is absent: an absent browser is an
environment fact, not a code defect.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from web.conftest import LIVE_FIELDS, NOW, Client, MasterDoubles
from web.terminal_input_fixture import HoldingRunner

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store
from shepherd.testkit.scripted_runner import ScriptedRunner

playwright_api = pytest.importorskip("playwright.sync_api")

if TYPE_CHECKING:
    from playwright.sync_api import Page

SESSION_NAME = "shp_eng-input"
ENGINE_SESSION_ID = "eng-input"
BOUND_S = 5.0

#: D6's sentence, the one limitation left in the note slot (`terminal.js`).
FIT_LIMITATION = (
    "the terminal is fitted to this window, not to the pane: a pane wider than "
    "this window has its lines re-wrapped here"
)


@pytest.fixture()
def scripted_runner() -> HoldingRunner:
    """An owned pane whose stream stays open, so there is a socket to type into."""
    from shepherd.core.runner import PaneState, ProcState
    from shepherd.runner.pane import parse_pane_fields, read_pane

    capture = (
        Path(__file__).resolve().parents[2]
        / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui"
        / "run-20260914T154946Z" / "03-after-stop.ansi"
    ).read_bytes()
    pane: PaneState = read_pane(capture, parse_pane_fields(LIVE_FIELDS), [])
    inner = ScriptedRunner(
        panes=(pane,),
        proc=ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW),
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
    return HoldingRunner(inner)


def _owned(store: Store) -> str:
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


#: REM-FIX 1 #4: what the page says, in order, when the pane refused a key —
#: the stream's notice **once** (hunter L1), then the refusal's own sentence (M5).
REFUSED_NOTICES = [
    "the terminal stream stopped — no more bytes will arrive",
    "input is off: the pane refused a key, so nothing more typed here reaches it",
]


def _open_terminal(page: Page, client: Client, session_id: str) -> None:
    """Navigate to the session and wait for the snapshot, so the socket is open."""
    page.goto(f"{client.origin}/")
    page.wait_for_timeout(700)
    page.locator('.nav-item[data-page="flock"]').click()
    page.wait_for_timeout(400)
    page.locator("#flock-projects .project").first.click()
    page.wait_for_timeout(300)
    page.locator(f'#flock-cards .card[data-session-id="{session_id}"]').click()
    page.locator("#session-terminal .xterm-screen").wait_for(timeout=BOUND_S * 1000)
    page.wait_for_function(
        "() => document.querySelector('#session-terminal .xterm-rows')"
        " && document.querySelector('#session-terminal .xterm-rows').textContent.trim() !== ''",
        timeout=BOUND_S * 1000,
    )


def test_a_refused_key_says_so_once(
    client: Client, store: Store, scripted_runner: HoldingRunner, master_doubles: MasterDoubles
) -> None:
    """The pane refuses the first key: the server closes with 1011, and the page
    says the stream stopped once and that the pane refused a key — not that the
    pane ended, and not the same notice twice."""
    from playwright.sync_api import sync_playwright

    from shepherd.core.runner import RunnerRefusal

    session_id = _owned(store)
    scripted_runner.fault = RunnerRefusal("tmux exited 1: command too long")
    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        _open_terminal(page, client, session_id)
        page.locator("#session-terminal .xterm-screen").click()
        page.keyboard.type("x")
        notices = page.locator("#session-terminal .terminal-degraded")
        deadline = time.monotonic() + BOUND_S
        while time.monotonic() < deadline and notices.count() < len(REFUSED_NOTICES):
            time.sleep(0.05)
        page.wait_for_timeout(300)
        assert notices.all_text_contents() == REFUSED_NOTICES
        assert scripted_runner.writes == []
        assert errors == [], errors
    finally:
        browser.close()
        play.stop()
        for stream in scripted_runner.streams:
            stream.close()


def test_keystrokes_in_the_emulator_are_sent_on_the_socket(
    client: Client, store: Store, scripted_runner: HoldingRunner, master_doubles: MasterDoubles
) -> None:
    from playwright.sync_api import sync_playwright

    session_id = _owned(store)
    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        # Arrival: the snapshot frame arrived, so the socket is open.
        _open_terminal(page, client, session_id)
        page.locator("#session-terminal .xterm-screen").click()
        page.keyboard.type("qa6")
        page.keyboard.press("Enter")

        deadline = time.monotonic() + BOUND_S
        while time.monotonic() < deadline and b"".join(scripted_runner.writes) != b"qa6\r":
            time.sleep(0.05)
        assert b"".join(scripted_runner.writes) == b"qa6\r", scripted_runner.writes

        # The page says nothing false: the input sentence is gone, D6's stays.
        note = page.locator("#session-input-note").text_content() or ""
        assert note == FIT_LIMITATION, note
        assert errors == [], errors
    finally:
        browser.close()
        play.stop()
        for stream in scripted_runner.streams:
            stream.close()
