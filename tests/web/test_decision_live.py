"""U17's decision card, driven in a real browser against the shipped page.

**Seam: the served page.** A module-graph walk answers *"did the browser fetch
this"* and never *"does anything call it"*, and a fixture that loads no module
cannot see what a module deletes — so the server is the shipped
`ThreadingHTTPServer` on loopback, the store is real, the route table is the
shipped one, the pane behind it is a **frozen capture**, and the browser is
chromium. Nothing is supplied by the test but the clicks.

**And it measures.** `tools/render_check.py` is structurally blind to layout
collapse: it asserts overflow, console errors and `must_see`, and reported *12
pages, 0 failures* over a Flock whose panes sat below the fold. The session pane
carried **no stylesheet rule at all** after T5.2's port and failed none of those
checks either. The only check that sees this is one that measures an element
against the viewport, so the phone case below does exactly that, at 390×844 —
the primary client.

Skipped, not failed, where chromium is absent: an uninstalled browser is an
environment fact, and reporting it as a code defect is the failure mode
`ENVIRONMENT not code` names.
"""

from __future__ import annotations

import pytest

from web.conftest import Client
from web.test_routes_decision import PERMISSION_CHOICES, _unparseable, owned, pane_of

from shepherd.core.fold_types import FoldDelta
from shepherd.core.runner import PaneState, ProcState
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.store.db import Store
from shepherd.store.models import Session
from shepherd.testkit.scripted_runner import ScriptedRunner

playwright_api = pytest.importorskip("playwright.sync_api")

from web.test_shell_live import DESKTOP, PHONE, _nav, _open  # noqa: E402

NOW = "2026-09-16T10:00:30Z"

#: §8's ask, the wording `tests/web/test_fleet_page.py` uses: what to do, never
#: "session needs attention".
IDLE_ASK = "waiting on a permission prompt"


@pytest.fixture()
def pane(request: pytest.FixtureRequest) -> PaneState:
    """The permission dialog, off the frozen capture, unless a test names another.

    Overridden by `@pytest.mark.parametrize("pane", [...], indirect=True)` with a
    `PaneState` — the trust capture, or a degradation no capture shows.
    """
    wanted = getattr(request, "param", None)
    return wanted if isinstance(wanted, PaneState) else pane_of("06-permission-dialog.ansi")


@pytest.fixture()
def scripted_runner(request: pytest.FixtureRequest, pane: PaneState) -> ScriptedRunner:
    """`pane` for the card's read; `request.param`, when given, for the reads after.

    The runner replays its panes in order and repeats the last, so a test can
    script "the card read a dialog, and by the time the answer arrived the pane
    had moved on" with no clock — the refusal D44's gates exist for.
    """
    after: tuple[PaneState, ...] = getattr(request, "param", ())
    return ScriptedRunner(
        panes=(pane, *after),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=b"",
        owned_panes=(),
    )


def needs_you(store: Store, session: Session) -> Session:
    """The one fact the card is keyed on (U11), written the way the fold does.

    `bucket_of` answers `needs_you` for a row whose effective state is
    `NEEDS_YOU` whatever else is true of it, so this is the whole of what makes
    a session one the page owes a card.
    """
    store.apply_fold_delta(
        session.id,
        FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=IDLE_ASK, last_event_at=NOW),
    )
    return session


def attached(store: Store) -> Session:
    """A session started in the user's own terminal: no pty of ours (E18)."""
    workspace = store.create_project(name="theirs", description=None)
    return store.register_session(
        engine_session_id="eng-attached",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )


def open_session(page, session_id: str) -> None:
    """What a person does: open the Flock, pick the project, click the card."""
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "flock")
    page.locator("#flock-projects .project").first.click()
    page.wait_for_timeout(300)
    card = page.locator(f'#flock-cards .card[data-session-id="{session_id}"]')
    assert card.count() == 1, page.locator("#flock-cards").inner_html()
    card.click()
    page.wait_for_timeout(700)


@pytest.fixture()
def desktop(client: Client, master_doubles):  # type: ignore[no-untyped-def]
    play, browser, page, errors = _open(client, DESKTOP)
    try:
        yield page, errors
    finally:
        browser.close()
        play.stop()


@pytest.fixture()
def phone(client: Client, master_doubles):  # type: ignore[no-untyped-def]
    play, browser, page, errors = _open(client, PHONE)
    try:
        yield page, errors
    finally:
        browser.close()
        play.stop()


def choice_rows(page) -> list[str]:
    """The card's choices as the DOM holds them.

    `text_content()`, never `inner_text()`: `.decision-head`, `.col-head` and
    friends are `text-transform: uppercase`, and `inner_text()` returns the
    transformed text — a comparison against the engine's own label would fail
    for a reason that has nothing to do with the card.
    """
    rows = page.locator("#session-decision .choice")
    return [rows.nth(index).text_content() for index in range(rows.count())]


def test_a_needs_you_session_shows_the_engines_own_prompt_in_the_browser(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """U11, driven. Three choices, the engine's own numbering, verbatim.

    The scope-carrying option — *"Yes, and always allow access to /tmp/… from
    this project"* — is the assertion that matters: it is the one a card
    flattened to approve/reject throws away, and it is on the page here or this
    test is red.
    """
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    open_session(page, session.id)

    card = page.locator("#session-decision")
    assert card.is_visible(), "the needs-you session got no card"
    rows = choice_rows(page)
    assert len(rows) == 3, rows
    for choice, rendered in zip(PERMISSION_CHOICES, rows, strict=True):
        assert str(choice["number"]) in rendered, (choice, rendered)
        assert choice["label"] in rendered, (choice, rendered)
    assert "always allow access" in " ".join(rows)
    assert errors == [], errors


def test_an_attached_session_renders_the_decision_read_only_in_the_browser(
    desktop, store: Store
) -> None:
    """E18: no pty of theirs, so no buttons — a sentence saying why instead."""
    page, errors = desktop
    session = needs_you(store, attached(store))
    open_session(page, session.id)

    card = page.locator("#session-decision")
    assert card.is_visible(), "an attached needs-you session got no card at all"
    assert "read-only" in (card.text_content() or "")
    assert page.locator("#session-decision .choice").count() == 0
    assert page.locator("#session-decision button").count() == 0
    assert errors == [], errors


def test_an_idle_session_gets_no_decision_card_in_the_browser(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """E20, driven: no card, and no pane read either.

    The runner records every call it is asked for, so "no card" is asserted as
    *nothing read this session's pane* rather than as *nothing is on screen* —
    a card built and hidden would pass the second and fail the first.
    """
    page, errors = desktop
    session = owned(store, scripted_runner)
    open_session(page, session.id)

    assert page.locator("#session-view").is_visible(), "the pane did not open"
    card = page.locator("#session-decision")
    assert not card.is_visible()
    assert (card.text_content() or "").strip() == ""
    assert scripted_runner.calls.count("pane") == 0, scripted_runner.calls
    assert errors == [], errors


def test_the_session_pane_is_laid_out_on_a_phone(
    phone, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """Part 2, measured at 390×844 — the primary client, and the one the
    `.legend-note` defect was invisible at.

    Three properties, each of which an unowned pane can fail while every
    existing check stays green:

    1. the pane **fills the column it is given** rather than sitting in a
       content-height box at the top of it;
    2. nothing inside it is wider than the column — a card whose choice labels
       carry a `/tmp/...` path is exactly where an unstyled pane scrolls
       sideways, which is why six other rules in `app.css` already say
       `overflow-wrap`;
    3. every slot a reader is supposed to read has a box with height, inside
       the viewport.
    """
    page, errors = phone
    session = needs_you(store, owned(store, scripted_runner))
    open_session(page, session.id)

    height = page.viewport_size["height"]
    width = page.viewport_size["width"]

    column = page.locator("#flock-detail")
    box = column.bounding_box()
    assert box is not None
    assert box["height"] > height * 0.6, (box, "the pane is below the fold")
    assert box["y"] + box["height"] <= height + 1, box

    overflow = page.evaluate(
        "() => { const n = document.getElementById('session-view');"
        " return [n.scrollWidth, n.clientWidth]; }"
    )
    assert overflow[0] <= overflow[1] + 1, (overflow, "the pane scrolls sideways at 390px")

    for slot in ("#session-title", "#session-chip", "#session-why", "#session-decision"):
        node = page.locator(slot)
        assert node.is_visible(), slot
        measured = node.bounding_box()
        assert measured is not None and measured["height"] > 0, (slot, measured)
        assert measured["x"] >= -1 and measured["x"] + measured["width"] <= width + 1, (
            slot,
            measured,
        )
    assert errors == [], errors



# ----- D77 (SD-06): a choice is clicked, and the existing route answers it ---


def permission_posts(page) -> list[object]:
    """Every POST the page sends to the answer route, as the wire carried it."""
    posts: list[object] = []
    page.on(
        "request",
        lambda request: posts.append(request.post_data_json)
        if request.method == "POST" and request.url.endswith("/permission")
        else None,
    )
    return posts


def outcome_of(page) -> str:
    """The card's answer line, once the reply has been painted into it."""
    note = page.locator("#session-decision [role=status]")
    note.wait_for(state="visible", timeout=5000)
    return note.text_content() or ""


def choice_buttons(page):  # type: ignore[no-untyped-def]
    return page.locator("#session-decision button.choice")


def test_clicking_a_permission_choice_posts_its_answer_once(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """Choice 2 — the scope-carrying one — reaches the pane as the key `2`.

    Three observations, none of them the page's own bookkeeping: the one POST
    the wire carried, the one key the runner was handed, and the outcome the
    server answered, painted on the card.
    """
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    posts = permission_posts(page)
    open_session(page, session.id)

    buttons = choice_buttons(page)
    assert buttons.count() == 3, page.locator("#session-decision").inner_html()
    buttons.nth(1).click()

    assert "answered" in outcome_of(page)
    assert posts == [{"choice": "approve_always"}], posts
    assert scripted_runner.writes == [b"2"], scripted_runner.writes
    assert errors == [], errors


def test_a_double_click_posts_once(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """PP12: one POST per click, however fast the second one lands."""
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    posts = permission_posts(page)
    open_session(page, session.id)

    choice_buttons(page).nth(2).dblclick()
    outcome_of(page)
    page.wait_for_timeout(500)

    assert posts == [{"choice": "deny"}], posts
    assert scripted_runner.writes == [b"3"], scripted_runner.writes
    assert errors == [], errors


@pytest.mark.parametrize("pane", [pane_of("01-trust-dialog.ansi")], indirect=True)
def test_the_trust_dialog_choices_stay_inert_and_say_why(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """D77: answering the trust screen changes what a folder may do from then on,
    so it keeps RD6's treatment — labelled, inert, and never posted."""
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    posts = permission_posts(page)
    open_session(page, session.id)

    card = page.locator("#session-decision")
    assert len(choice_rows(page)) == 2, card.inner_html()
    assert page.locator("#session-decision button").count() == 0
    text = card.text_content() or ""
    assert "No, exit" in text
    assert "press the option in the session's own terminal" in text
    page.locator("#session-decision .choice").first.click()
    page.wait_for_timeout(500)
    assert posts == [], posts
    assert scripted_runner.writes == [], scripted_runner.writes
    assert errors == [], errors


@pytest.mark.parametrize(
    ("label", "answer"), [("approve", "approve"), ("reject", "deny")]
)
@pytest.mark.parametrize("pane", [_unparseable()], indirect=True)
def test_an_unreadable_permission_screen_answers_approve_and_reject_through_the_same_route(
    desktop, store: Store, scripted_runner: ScriptedRunner, label: str, answer: str
) -> None:
    """The two unnumbered options post a **word**, never a position.

    The server still decides whether the screen is the option set it captured
    (`is_the_captured_permission_dialog`), so whatever it answers — a key or a
    refusal — is what the card shows.
    """
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    posts = permission_posts(page)
    open_session(page, session.id)

    buttons = choice_buttons(page)
    assert buttons.count() == 2, page.locator("#session-decision").inner_html()
    page.locator("#session-decision button.choice", has_text=label).click()

    assert outcome_of(page).strip() != ""
    assert posts == [{"choice": answer}], posts
    assert errors == [], errors


@pytest.mark.parametrize(
    "scripted_runner", [(pane_of("03-after-stop.ansi"),)], indirect=True
)
def test_a_refused_answer_is_shown_on_the_card(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """The dialog was answered in the terminal before the click landed.

    The server re-reads the pane, finds no dialog, sends nothing, and says so —
    and that sentence is on the card, with the choices offered again.
    """
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    posts = permission_posts(page)
    open_session(page, session.id)

    choice_buttons(page).first.click()
    shown = outcome_of(page)

    assert "not a permission dialog" in shown, shown
    assert posts == [{"choice": "approve"}], posts
    assert scripted_runner.writes == [], scripted_runner.writes
    assert choice_buttons(page).first.is_enabled()
    assert errors == [], errors


def test_a_reply_for_a_card_no_longer_open_paints_nothing(
    desktop, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """BC-12's intent rule: the reply is held until the pane has been re-opened.

    The card it answered is gone; the card on screen now asked nothing, so it
    shows no outcome and keeps its choices live. And while the first answer is
    still out, the re-opened card posts nothing of its own.
    """
    page, errors = desktop
    session = needs_you(store, owned(store, scripted_runner))
    held: list[object] = []
    page.route("**/permission", lambda route: held.append(route))
    open_session(page, session.id)

    choice_buttons(page).first.click()
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert len(held) == 1, "the click never reached the wire"

    # Re-opened by the card, not by `open_session`: a reload would take the
    # fetch — and the module that awaits it — down with the old page.
    page.locator(f'#flock-cards .card[data-session-id="{session.id}"]').click()
    page.wait_for_timeout(700)
    # The re-opened card is live, but its session's answer is still out: a
    # click on it posts nothing (PP12 across cards, not only within one).
    choice_buttons(page).first.click()
    page.wait_for_timeout(300)
    assert len(held) == 1, "a second answer was posted while the first was in flight"
    held[0].continue_()  # type: ignore[attr-defined]
    page.wait_for_timeout(700)

    assert page.locator("#session-decision [role=status]:visible").count() == 0
    assert choice_buttons(page).count() == 3
    assert choice_buttons(page).first.is_enabled()
    assert errors == [], errors
