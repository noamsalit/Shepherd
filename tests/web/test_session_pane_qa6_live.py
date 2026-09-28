"""QA round 6, phase P12 — the session pane, driven in a real browser.

Four bug candidates from `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md`
§8, each proved at the page: the shipped `index.html` from the real
`ThreadingHTTPServer` on a loopback ephemeral port, the real modules, chromium.

- **BC-13** (U45): the card follows a state change in 0.025 s while the open
  session's header keeps `running` / `—`. The header is re-read by the same
  refresh an event causes, and the terminal is never touched by it.
- **BC-36** (U11, B10): opening an owned session Shepherd killed opened a
  terminal WebSocket that 404s. Keyed on `stop_reason == "killed"`, **never on
  `ended_at`** — every turn end stamps `ended_at` on a live pane, so B9's
  post-turn session must still open exactly one socket.
- **BC-25, rename half** (U13): Escape after a completed rename repainted the
  pre-rename title, and a double Enter posted two renames.
- **BC-12 R3**: a slow rename reply for session A painted A's new title into
  session B's open header.

Every wait is a DOM or network fact (a `wait_for_function`, a parked fetch's
own counter, a `setTimeout` queued behind the reply's paint) — never a count of
requests standing in for a render (HI-4). Skipped, not failed, where chromium
is absent — an environment fact.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from web.conftest import NOW, Client, MasterDoubles
from web.test_shell import render_check_constant

from shepherd.core.fold_types import FoldDelta
from shepherd.core.runner import EngineCapabilities, RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store
from shepherd.store.models import Session
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner
from shepherd.toolsurface.tools_rename import register_rename_tool

playwright_api = pytest.importorskip("playwright.sync_api")

DESKTOP = {
    name: {"width": width, "height": height}
    for name, width, height in render_check_constant("VIEWPORTS")  # type: ignore[misc]
}["desktop"]

#: The sentence a killed owned session's pane owes its reader (BC-36). Spelled
#: here independently of `session.js` — the spec for the fix, not a read-back.
KILLED_BANNER = "this session was killed — its terminal is gone"

#: §8's ask, the wording the fleet tests use.
ASK = "waiting on a permission prompt"

#: How long a header may take to follow an event. The card follows in tens of
#: milliseconds on this page (U45's control); five seconds is a bound, not a pace.
FOLLOW_MS = 5000


class Browser:
    """One chromium page on the shipped index, closed by `close()`.

    It keeps what the page did at the socket: every WebSocket it opened (URL)
    and every console error — the U11 defect *was* a console error.
    """

    def __init__(self, client: Client) -> None:
        from playwright.sync_api import sync_playwright

        self._play = sync_playwright().start()
        try:
            self._browser = self._play.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
            self._play.stop()
            pytest.skip(f"chromium is not available: {exc}")
        self.page = self._browser.new_page(viewport=DESKTOP)
        self.errors: list[str] = []
        self.sockets: list[str] = []
        self.page.on("pageerror", lambda error: self.errors.append(f"pageerror: {error}"))
        self.page.on(
            "console",
            lambda message: self.errors.append(f"console: {message.text}")
            if message.type == "error"
            else None,
        )
        self.page.on("websocket", lambda socket: self.sockets.append(socket.url))
        self.page.goto(f"{client.origin}/")
        self.page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")

    def close(self) -> None:
        self._browser.close()
        self._play.stop()


@pytest.fixture()
def desktop(client: Client, master_doubles: MasterDoubles) -> Iterator[Browser]:
    opened = Browser(client)
    try:
        yield opened
    finally:
        opened.close()


#: D29's ceiling as the composition root hands it over: `can_set_title` off, so
#: every rename here is the local one (DP1) — the path the pane renders.
RENAME_CEILING = EngineCapabilities(
    can_spawn=True,
    can_steer=True,
    can_fork=True,
    can_set_title=False,
    has_hooks=True,
    effort_ladder=("low", "medium", "high", "xhigh", "max"),
    transcript_format="jsonl",
)


@pytest.fixture(autouse=True)
def rename_tool(
    tools: None, store: Store, scripted_runner: ScriptedRunner, tmp_path: Path
) -> None:
    """`rename_session`, which the shared `tools` fixture does not register.

    The composition root registers it beside T18's twelve (`compose.py`); the
    web conftest predates the pane driving it, so this module adds it after
    `tools` has run, the way the root does, with the same injections.
    """
    register_rename_tool(
        store=store,
        runner=scripted_runner,
        now=lambda: NOW,
        config_dir=tmp_path / "engine-config",
        capabilities=RENAME_CEILING,
    )


# ----- the rows ---------------------------------------------------------------
#
# Rows written inside a test land after the page's first read, so those tests
# reload before opening the Flock; the fixture-built pair below is requested
# **ahead of** `desktop`, so the first read already carries it (P11's lesson).


@pytest.fixture()
def project(store: Store) -> str:
    return store.create_project(name="qa6-pane", description=None).id


def attached_session(store: Store, project: str, engine_id: str) -> Session:
    row = store.register_session(
        engine_session_id=engine_id,
        workspace_id=project,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    store.apply_fold_delta(row.id, FoldDelta(state=SessionState.RUNNING, last_event_at=NOW))
    return row


def owned_session(store: Store, runner: ScriptedRunner, project: str, engine_id: str) -> Session:
    """A session with a pane of ours: the row carries the handle, the runner lists it."""
    row = store.register_session(
        engine_session_id=engine_id,
        workspace_id=project,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.USER_UI,
        ownership=Ownership.OWNED,
    )
    name = f"shepherd_{row.id}"
    store.set_runner_handle(
        row.id, RunnerHandle(runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=name)
    )
    runner.live[name] = PaneRef(session_name=name, session_id=row.id, pane_pid=4041880, dead=False)
    return row


def stop(store: Store, row: Session, reason: StopReason, bucket: Bucket) -> None:
    """The stop verdict and `state stopped`, as a turn end or a kill leaves them."""
    store.apply_stop_verdict(
        session_id=row.id,
        verdict=Verdict(
            stop_reason=reason,
            bucket=bucket,
            why=f"qa6 {reason.value}",
            confidence=1.0,
            decided_by=DecidedBy.DECLARED,
            next_actions=(),
            waiting_on=None,
            missing=(),
        ),
        ended_at="2026-09-16T10:00:20.000Z",
        exit_code=None,
    )
    store.apply_fold_delta(row.id, FoldDelta(state=SessionState.STOPPED, last_event_at=NOW))


def publish_state(session: Session) -> None:
    from shepherd.core.clock import utc_now
    from shepherd.core.stream import StreamEvent
    from shepherd.toolsurface.stream import publish

    publish(
        StreamEvent(
            kind="session.state",
            session_id=session.id,
            payload={"state": "needs_you"},
            occurred_at=utc_now(),
        )
    )


def text(page: object, selector: str) -> str:
    return str(page.locator(selector).text_content() or "")  # type: ignore[attr-defined]


def open_session(page: object, session: Session) -> None:
    """What a person does: the Flock, the card, and the pane's header for it."""
    page.locator("#nav-fleet").click()  # type: ignore[attr-defined]
    card = f'#flock-cards [data-session-id="{session.id}"]'
    page.wait_for_selector(card)  # type: ignore[attr-defined]
    page.locator(card).click()  # type: ignore[attr-defined]
    page.wait_for_function(  # type: ignore[attr-defined]
        """(id) => document.querySelector(`#flock-cards [data-session-id="${id}"]`)
                     ?.getAttribute("aria-current") === "true"
                   && !document.getElementById("session-view").hidden""",
        arg=session.id,
    )


def terminal_sockets(desktop: Browser, session: Session) -> list[str]:
    return [url for url in desktop.sockets if f"/api/sessions/{session.id}/terminal" in url]


# ----- BC-13: the header follows the session's state -----------------------------


def wait_for_header(page: object, state: str) -> bool:
    try:
        page.wait_for_function(  # type: ignore[attr-defined]
            '(state) => document.getElementById("session-state").textContent === state',
            arg=state,
            timeout=FOLLOW_MS,
        )
    except Exception:  # noqa: BLE001 - a timeout is the observation, asserted below
        return False
    return True


def test_the_header_follows_a_state_change(
    store: Store, project: str, desktop: Browser
) -> None:
    """U45. The open session goes needs_you; its header says so, with the ask."""
    session = attached_session(store, project, "eng-follow")
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    open_session(page, session)
    assert text(page, "#session-state") == "running"

    store.apply_fold_delta(
        session.id,
        FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=ASK, last_event_at=NOW),
    )
    publish_state(session)

    followed = wait_for_header(page, "needs_you")
    header = {
        "state": text(page, "#session-state"),
        "chip": text(page, "#session-chip"),
        "why": text(page, "#session-why"),
    }
    assert followed, f"the header did not follow within {FOLLOW_MS} ms: {header}"
    assert header == {"state": "needs_you", "chip": "needs_you", "why": ASK}, header
    assert desktop.errors == [], desktop.errors


def test_a_header_refresh_leaves_an_open_rename_alone(
    store: Store, project: str, desktop: Browser
) -> None:
    """The refresh repaints the header, never the input a person is typing in."""
    session = attached_session(store, project, "eng-typing")
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    open_session(page, session)

    page.locator("#session-rename").click()
    page.locator("#session-title input").fill("half-typed")
    store.apply_fold_delta(
        session.id,
        FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=ASK, last_event_at=NOW),
    )
    publish_state(session)

    assert wait_for_header(page, "needs_you"), text(page, "#session-state")
    assert page.locator("#session-title input").input_value() == "half-typed"
    assert desktop.errors == [], desktop.errors


# ----- BC-36 / B9 / B10: a killed pane has no terminal; a finished turn does ----------


@pytest.fixture()
def killed_and_finished(
    store: Store, scripted_runner: ScriptedRunner, project: str
) -> tuple[Session, Session]:
    """Two owned rows: one Shepherd killed, one alive after finishing a turn."""
    killed = owned_session(store, scripted_runner, project, "eng-killed")
    stop(store, killed, StopReason.KILLED, Bucket.UNFINISHED)
    finished = owned_session(store, scripted_runner, project, "eng-finished")
    stop(store, finished, StopReason.COMPLETED, Bucket.FINISHED)
    return killed, finished


def test_a_killed_owned_session_opens_no_socket(
    killed_and_finished: tuple[Session, Session], desktop: Browser
) -> None:
    """B10 at the page: the killed banner, no socket, no console error.

    "No socket" needs a positive signal, because `openTerminal` opens its socket
    after an `await`. The control is the finished session opened next: its
    socket is observed, and a socket the killed pane had started would have been
    constructed first — so the killed one's absence is read after a fact.
    """
    killed, finished = killed_and_finished
    page = desktop.page
    open_session(page, killed)
    assert text(page, "#session-banner") == KILLED_BANNER
    assert page.locator("#session-banner").is_visible()
    assert not page.locator("#session-terminal").is_visible()

    with page.expect_websocket(lambda socket: finished.id in socket.url):
        open_session(page, finished)

    assert terminal_sockets(desktop, killed) == [], desktop.sockets
    assert [error for error in desktop.errors if killed.id in error or "pageerror" in error] == []


def test_a_live_session_that_finished_a_turn_still_opens_its_terminal(
    killed_and_finished: tuple[Session, Session], desktop: Browser
) -> None:
    """B9: `ended_at` set, `state stopped`, `stop_reason completed` — one socket.

    The guard against the discriminator the plan review rejected: keying the
    suppression on `ended_at` would hide the terminal of every session that has
    answered once.
    """
    _, finished = killed_and_finished
    page = desktop.page
    with page.expect_websocket(lambda socket: finished.id in socket.url):
        open_session(page, finished)
    assert not page.locator("#session-banner").is_visible()
    assert page.locator("#session-terminal").is_visible()
    assert len(terminal_sockets(desktop, finished)) == 1, desktop.sockets


def test_a_header_refresh_does_not_reopen_the_terminal(
    store: Store, killed_and_finished: tuple[Session, Session], desktop: Browser
) -> None:
    """BC-13's other half: the header follows, and the terminal is not touched."""
    _, finished = killed_and_finished
    page = desktop.page
    with page.expect_websocket(lambda socket: finished.id in socket.url):
        open_session(page, finished)

    store.apply_fold_delta(
        finished.id,
        FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=ASK, last_event_at=NOW),
    )
    publish_state(finished)
    assert wait_for_header(page, "needs_you"), text(page, "#session-state")
    assert len(terminal_sockets(desktop, finished)) == 1, desktop.sockets
    assert page.locator("#session-terminal").is_visible()


# ----- BC-25 (rename) and BC-12 R3 ------------------------------------------------

#: Parks every `/rename` POST until `__release()`, counts the parked ones in
#: `__held`, and queues a `setTimeout` behind each released reply's body read —
#: `window.__painted` turns true only after the product's own continuation, the
#: code that paints, has run.
PARK_RENAMES = """() => {
  const real = window.fetch;
  const held = [];
  window.__held = held;
  window.__painted = 0;
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!/\\/rename$/.test(url)) {
      return real.call(window, input, init);
    }
    return new Promise((resolve, reject) => {
      held.push(() =>
        real.call(window, input, init).then((response) => {
          const json = response.json.bind(response);
          response.json = () => json().then((body) => {
            setTimeout(() => { window.__painted += 1; }, 0);
            return body;
          });
          resolve(response);
        }, reject)
      );
    });
  };
  window.__release = () => {
    const queued = held.splice(0, held.length);
    for (const send of queued) { send(); }
    return queued.length;
  };
}"""


def rename_to(page: object, title: str) -> None:
    page.locator("#session-rename").click()  # type: ignore[attr-defined]
    page.locator("#session-title input").fill(title)  # type: ignore[attr-defined]
    page.locator("#session-title input").press("Enter")  # type: ignore[attr-defined]


def test_escape_after_a_rename_shows_the_new_title(
    store: Store, project: str, desktop: Browser
) -> None:
    """U13: rename to R1, then ✎ and Escape — twice. The header reads R1 each time."""
    session = attached_session(store, project, "eng-escape")
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    open_session(page, session)

    rename_to(page, "QA6 R1")
    page.wait_for_function('() => document.getElementById("session-title").textContent === "QA6 R1"')

    for _ in range(2):
        page.locator("#session-rename").click()
        page.locator("#session-title input").press("Escape")
        assert text(page, "#session-title") == "QA6 R1"
    assert desktop.errors == [], desktop.errors


def test_a_double_enter_posts_one_rename(store: Store, project: str, desktop: Browser) -> None:
    """U13: Enter twice while the first rename is in flight posts one rename."""
    session = attached_session(store, project, "eng-double")
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    open_session(page, session)
    page.evaluate(PARK_RENAMES)

    page.locator("#session-rename").click()
    page.locator("#session-title input").fill("QA6 R2")
    page.locator("#session-title input").press("Enter")
    page.locator("#session-title input").press("Enter")
    posted = page.evaluate("() => window.__held.length")

    page.evaluate("() => window.__release()")
    page.wait_for_function("() => window.__painted >= 1")
    assert posted == 1, f"{posted} renames posted for one title"
    assert text(page, "#session-title") == "QA6 R2"

    # …and the flag is released with the reply: the next rename posts again.
    rename_to(page, "QA6 R3")
    assert page.evaluate("() => window.__held.length") == 1
    page.evaluate("() => window.__release()")
    page.wait_for_function("() => window.__painted >= 2")
    assert text(page, "#session-title") == "QA6 R3"


def test_a_slow_rename_reply_does_not_paint_another_session(
    store: Store, project: str, client: Client, desktop: Browser
) -> None:
    """R3: A's rename reply lands while B is open; B's header keeps B's title."""
    first = attached_session(store, project, "eng-r3-a")
    second = attached_session(store, project, "eng-r3-b")
    answer = client.post(f"/api/sessions/{second.id}/rename", {"title": "QA6 R session B"})
    assert answer.status == 200, answer.body
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    page.evaluate(PARK_RENAMES)

    open_session(page, first)
    rename_to(page, "QA6-A-NEW")
    assert page.evaluate("() => window.__held.length") == 1

    open_session(page, second)
    assert text(page, "#session-title") == "QA6 R session B"

    page.evaluate("() => window.__release()")
    page.wait_for_function("() => window.__painted >= 1")
    assert text(page, "#session-title") == "QA6 R session B"
    assert text(page, "#session-rename-status") == ""
    assert desktop.errors == [], desktop.errors


# ----- REMFIX-1 #1: a header refresh keeps an open `why?` and the focus -------------


def test_a_header_refresh_keeps_an_open_why_and_the_focus(
    store: Store, project: str, desktop: Browser
) -> None:
    """BC-13's refresh redrew the actions slot on every event, for any session.

    A reader who had opened `why?` and tabbed to an action lost both the moment
    **another** session's event arrived: `replaceChildren` built a new, closed
    disclosure and the focused link was detached, so focus fell to `<body>`.
    The actions and the evidence did not change, so nothing in the slot may.
    The positive signal that the refresh ran is A's title, changed in the store
    before B's event and painted by the same header pass.
    """
    from shepherd.core.stops import ActionSource, NextAction, NextActionKind

    reading = attached_session(store, project, "eng-why-a")
    other = attached_session(store, project, "eng-why-b")
    store.apply_stop_verdict(
        session_id=reading.id,
        verdict=Verdict(
            stop_reason=StopReason.COMPLETED,
            bucket=Bucket.FINISHED,
            why="qa6 remfix why",
            confidence=0.5,
            decided_by=DecidedBy.DECLARED,
            next_actions=(
                NextAction(
                    text="open the docs",
                    kind=NextActionKind.EXTERNAL,
                    target="https://example.invalid/docs",
                    source=ActionSource.DECLARED,
                ),
            ),
            waiting_on=None,
            missing=(),
        ),
        ended_at="2026-09-16T10:00:20.000Z",
        exit_code=None,
    )
    store.apply_fold_delta(reading.id, FoldDelta(state=SessionState.STOPPED, last_event_at=NOW))
    page = desktop.page
    page.reload()
    page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")
    open_session(page, reading)

    page.locator("#session-actions .why-summary").click()
    assert page.locator("#session-actions details.why-note").get_attribute("open") is not None
    page.locator("#session-actions a.action-link").focus()
    assert page.evaluate(
        "() => document.activeElement?.classList.contains('action-link') === true"
    )

    store.apply_title(reading.id, "QA6 refreshed", "user")
    publish_state(other)
    page.wait_for_function(
        '() => document.getElementById("session-title").textContent === "QA6 refreshed"',
        timeout=FOLLOW_MS,
    )

    kept = page.evaluate(
        """() => ({
             open: document.querySelector("#session-actions details.why-note")?.open === true,
             focused: document.activeElement?.classList.contains("action-link") === true,
             inside: document.getElementById("session-actions")
                       .contains(document.activeElement),
           })"""
    )
    assert kept == {"open": True, "focused": True, "inside": True}, kept
    assert desktop.errors == [], desktop.errors
