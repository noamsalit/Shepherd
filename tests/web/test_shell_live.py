"""The integration pass: the **shipped** shell, driven in a real browser.

Every other module in `tests/web/` proves the front end by reading bytes — the
shipped JS parsed and never executed, plus HTTP through `invoke()`. Phases 6, 7
and 9 were built in parallel worktrees against `fixtures/shell_harness.html`, a
fixture that loads no module at all, so **no line of any page's JavaScript had
ever run** before this file. Four pages built against a contract and never
executed is exactly where the surprises are, and this is where they surface.

What is real here, named because that is the whole claim: the server is the
shipped `ThreadingHTTPServer` on a loopback port, the page is the shipped
`src/shepherd/web/static/index.html` fetched from `/`, the modules are fetched
from `/static/` by that server, the data is a real store behind the real route
table, and the browser is chromium. Nothing is supplied by the test but the
clicks.

Skipped, not failed, where chromium is absent: a browser that is not installed
is an environment fact, and reporting it as a code defect is the failure mode
`ENVIRONMENT not code` names.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from web.conftest import Client, MasterDoubles, hold_fetches, seed
from web.test_shell import render_check_constant

from shepherd.core.states import Origin, Ownership
from shepherd.store.db import Store
from shepherd.store.models import Session

playwright_api = pytest.importorskip("playwright.sync_api")

#: Every viewport `tools/render_check.py` declares, **read out of that file**
#: rather than re-spelled. The comment here used to say "read out of that file"
#: while spelling two literals below it, and that was the whole of the hole QA
#: run 3 walked through: the constant grew a width and no test would have
#: noticed. `_viewports()` derives the mapping, so a width added at the one
#: definition site is a width this module drives.
VIEWPORTS = {
    name: {"width": width, "height": height}
    for name, width, height in render_check_constant("VIEWPORTS")  # type: ignore[misc]
}
PHONE = VIEWPORTS["phone"]
DESKTOP = VIEWPORTS["desktop"]


def _open(
    client: Client,
    viewport: dict[str, int],
    *,
    touch: bool = False,
    init_script: str | None = None,
):
    """A chromium page on the shipped index, with its console collected.

    `touch` gives the context a real touchscreen, which is the only way to ask
    a phone question honestly: `page.click()` synthesises a mouse, and a mouse
    has a `hover` a finger does not. `init_script` runs **before any module of
    the page does**, which is what makes an `addEventListener` spy able to see
    a binding that happens at import time.
    """
    from playwright.sync_api import sync_playwright

    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
    page = browser.new_page(viewport=viewport, has_touch=touch)
    if init_script is not None:
        page.add_init_script(init_script)
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
    return play, browser, page, errors


@pytest.fixture()
def desktop(client: Client, master_doubles: MasterDoubles):
    play, browser, page, errors = _open(client, DESKTOP)
    try:
        yield page, errors
    finally:
        browser.close()
        play.stop()


@pytest.fixture()
def phone(client: Client, master_doubles: MasterDoubles):
    play, browser, page, errors = _open(client, PHONE)
    try:
        yield page, errors
    finally:
        browser.close()
        play.stop()


def _nav(page, target: str) -> None:
    """Open a page the way a person does, through the drawer on a phone."""
    # `<=`, not `<`: the drawer's media query is `max-width: 760px`, which is
    # inclusive. Latent while only 390 and 1280 were driven; a real off-by-one
    # the moment this helper is handed a width it has not seen before.
    if page.viewport_size["width"] <= 760:
        page.locator("#drawer-open").click()
        page.wait_for_timeout(200)
    page.locator(f'.nav-item[data-page="{target}"]').click()
    page.wait_for_timeout(400)


def test_the_shipped_page_runs_every_module_it_loads(desktop) -> None:
    """Arrival, and the first execution of any of this JavaScript.

    A page that threw on its first import passes every absence assertion below
    — the elements it would have built are simply not there — so the console is
    read before anything is asked of the DOM.
    """
    page, errors = desktop
    assert errors == [], errors
    # …and the bootstrap really ran: `showPage` is what reveals Shepherd, and
    # the static markup ships the Flock visible instead.
    assert page.locator("#page-shepherd").is_visible()
    assert page.locator('[id^="page-"]:visible').count() == 1


def test_every_page_opens_and_shows_its_own_name(desktop) -> None:
    """The `must_see` contract, against the served page rather than a fixture.

    The six names come out of `tools/render_check.py`; a second list here would
    be the drift wearing a test's clothes.
    """
    page, errors = desktop
    pages = render_check_constant("PAGES")
    assert isinstance(pages, list) and len(pages) == 6, pages
    missing: list[str] = []
    for target, must_see in pages:
        _nav(page, target)
        root = page.locator(f"#page-{target}")
        if not root.is_visible():
            missing.append(f"{target} did not open")
            continue
        if page.locator('[id^="page-"]:visible').count() != 1:
            missing.append(f"{target}: more than one root visible")
        if must_see not in root.inner_text():
            missing.append(f"{target} is missing {must_see!r}")
    assert missing == [], missing
    assert errors == [], errors


def test_the_stop_summary_survives_a_phone(phone) -> None:
    """Principle 5 on the primary client, measured rather than read.

    `#stop-summary` carried `class="legend-note"` and `app.css` hides
    `.legend-note` below 900px, so the unknown rate, the low-confidence count
    and the never-classified count were **absent on a phone** — on the page
    that is also the root shipping visible. `render_check.py` could not see it:
    it asserts overflow and console errors, not the visibility of one element.

    All three values are measured, not just the strip, because a strip that is
    laid out and clipped to zero height is not a displayed number either.
    """
    page, errors = phone
    _nav(page, "flock")
    strip = page.locator("#stop-summary")
    assert strip.count() == 1
    assert strip.is_visible(), "principle 5's three numbers are hidden on a phone"
    for slot in ("#unknown-rate", "#low-confidence", "#unclassified"):
        node = page.locator(slot)
        assert node.is_visible(), slot
        box = node.bounding_box()
        assert box is not None and box["height"] > 0, (slot, box)
    assert errors == [], errors


def test_a_card_click_opens_the_session_pane(desktop, store: Store) -> None:
    """D67's third pane, driven: a card carries its id and the shell reads it.

    The whole chain runs for the first time here — `app.js` reads the tree,
    `flock.js` builds a project button and a card, the shell reads the card's
    own `data-session-id`, reads that session through the API and hands the
    projection to `renderSession`, which walks the drill-down to `detail`.
    """
    page, errors = desktop
    session = seed(store)
    _nav(page, "flock")
    # An event is what re-reads in the product; a nav click is what a person
    # does, and the Flock reads on the first paint, so the page is re-opened
    # rather than waited on a timer.
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "flock")

    project = page.locator("#flock-projects .project").first
    assert project.count() == 1, page.locator("#flock-projects").inner_html()
    project.click()
    page.wait_for_timeout(300)

    card = page.locator(f'#flock-cards .card[data-session-id="{session.id}"]')
    assert card.count() == 1, page.locator("#flock-cards").inner_html()
    card.click()
    page.wait_for_timeout(500)

    assert page.locator("#session-view").is_visible()
    assert page.locator("#page-flock").get_attribute("data-level") == "detail"
    assert errors == [], errors


def test_the_projects_page_builds_itself_and_its_session_link_opens_the_flock(
    desktop, store: Store
) -> None:
    """T9.1's contract points 1 and 5, driven end to end.

    `#page-projects` ships empty and `mountProjects()` builds both panes and
    both dialogs inside it — so a shell that also declared `#dlg-project` would
    leave the page opening an empty dialog belonging to nobody. Then the link:
    the Projects page performs no navigation of its own, and the shell is what
    turns a `[data-page]` anchor into a page change plus a selected session.
    """
    page, errors = desktop
    session = seed(store)
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "projects")

    assert page.locator("#page-projects #proj-list .proj-row").count() >= 1
    # Built inside the root it clears, exactly once each.
    for dialog in ("#dlg-project", "#dlg-delete"):
        assert page.locator(dialog).count() == 1, dialog
        assert page.locator(f"#page-projects {dialog}").count() == 1, dialog

    page.locator("#proj-list .proj-row").first.click()
    page.wait_for_timeout(400)
    link = page.locator('#proj-detail .mini-open[data-page="flock"]').first
    assert link.count() == 1, page.locator("#proj-detail").inner_html()
    assert link.get_attribute("data-session-id") == session.id

    link.click()
    page.wait_for_timeout(600)
    assert page.locator("#page-flock").is_visible()
    assert page.locator('[id^="page-"]:visible').count() == 1
    assert page.locator("#session-view").is_visible()
    assert page.locator("#session-title").inner_text() != ""
    assert errors == [], errors


def test_the_two_pane_pages_drill_down_on_a_phone(phone) -> None:
    """U9's drill-down on `.panes2`, measured on both pages that use it.

    `app.css` hides every child of a `.panes2` below 760px and reveals one back
    by `data-level`, which is the whole of the phone's back behaviour. The rule
    is `.panes2 > *`, and **`.set-panel { display: flex }` is declared 155 lines
    later at equal specificity** — so Settings showed its nav *and* its panel
    stacked on a phone, with a back chevron in the middle of the page and
    nothing to go back from. Projects, whose panel carries no second class, was
    fine. A rule that one page silently outranks is not a rule, so it is
    asserted on both pages rather than on the one that was broken.
    """
    page, errors = phone
    for target, first, second in (
        ("projects", "#page-projects .herd-col", "#page-projects .proj-detail"),
        ("settings", "#page-settings .herd-col", "#page-settings .proj-detail"),
    ):
        _nav(page, target)
        assert page.locator(first).is_visible(), f"{target}: the list pane is not shown"
        assert not page.locator(second).is_visible(), (
            f"{target}: both panes are visible at 390px — the drill-down is a no-op"
        )
    assert errors == [], errors


def test_each_page_root_fills_the_column_it_is_given(desktop) -> None:
    """The survivor, closed: a page laid out **off the bottom of the screen**.

    Two of the five defects this pass found were this shape, and the whole
    existing suite was blind to both. `.herd` declared two grid rows while
    carrying three full-width items, so the stop band took the flexible row and
    the panes were pushed below the fold; `.detail` carries no `flex: 1`, so the
    Shepherd page was a content-height box at the top of an empty column with
    its composer unpinned. Reverting either mutation turns **nothing** red
    except the byte-freeze digest — `render_check.py` reports 12 pages and 0
    failures over both, because nothing overflows horizontally, nothing throws,
    and each page still names itself.

    So the property is measured rather than inferred: a page root's panes reach
    the bottom of the viewport, and the composer sits at it. The thresholds are
    deliberately loose — this is a check for *collapsed*, not a pixel
    comparison, and 105px of 900 is what the defect looked like.
    """
    page, errors = desktop
    height = page.viewport_size["height"]

    _nav(page, "flock")
    for pane in (".col-projects", ".col-sessions", ".col-detail"):
        box = page.locator(f"#page-flock {pane}").bounding_box()
        assert box is not None, pane
        assert box["height"] > height * 0.6, (pane, box, "the panes are below the fold")
        assert box["y"] + box["height"] <= height + 1, (pane, box)

    _nav(page, "shepherd")
    composer = page.locator("#page-shepherd .composer-wrap").bounding_box()
    assert composer is not None
    assert composer["y"] + composer["height"] > height * 0.8, (
        composer,
        "the composer is not pinned to the bottom of the page",
    )
    assert errors == [], errors


# ============================================================================
# The QA remediation pass (workflow wf-20260921T212808Z-9172ed6b).
#
# Three defects live in `app.js` and in the shell's markup, and none of them is
# visible from a fixture: they are about what the *stream* does to the page.
# `publish` writes into the same ring `/api/events` serves, so an envelope here
# arrives at the browser over the real transport.
# ============================================================================


def publish_events(count: int, kind: str = "qa.burst") -> None:
    """`count` envelopes through the real ring, as the composition root does."""
    from shepherd.core.clock import utc_now
    from shepherd.core.stream import StreamEvent
    from shepherd.toolsurface.stream import publish

    for n in range(count):
        publish(
            StreamEvent(
                kind=kind, session_id=None, payload={"n": n}, occurred_at=utc_now()
            )
        )


def test_the_connection_state_is_not_destroyed_by_the_first_event(desktop) -> None:
    """**Defect 5 (MEDIUM).** `#stream-status` had three writers and three
    vocabularies: `sse.js` wrote `live`/`reconnecting`/`unreadable`, `app.js`
    wrote the **raw event kind** on every envelope, and `app.js` also wrote
    failures there. QA measured one page load going
    `live` -> `no such session: …` -> `qa.burst`.

    So the connection indicator — the one thing on the page that says whether
    Shepherd is still there — was destroyed by the first event that arrived,
    and replaced by a word from a different vocabulary. The slot is the
    stream's state and only the stream writes it.
    """
    page, errors = desktop
    status = page.locator("#stream-status")
    assert status.inner_text() == "live", status.inner_text()

    publish_events(3)
    page.wait_for_timeout(600)

    assert status.inner_text() == "live", status.inner_text()
    assert errors == [], errors


def test_an_error_persists_until_it_is_superseded_or_dismissed(desktop) -> None:
    """The other half of defect 5, and the one that cost information.

    The **only** place a `correlation_id` is ever shown to a person is a failed
    read, and it was written into the same slot the next envelope overwrote —
    measured at roughly 35ms under QA's burst. An id nobody can finish reading
    is an id nobody can quote, which is the whole of what §13 leaves behind
    after a failed tool call.
    """
    from shepherd.toolsurface.registry import GENERIC_ERROR

    page, errors = desktop
    page.route(
        "**/api/fleet",
        lambda route: route.fulfill(
            status=400,
            content_type="application/json",
            body=(
                '{"ok": false, "data": null, "error": "'
                + GENERIC_ERROR
                + '", "correlation_id": "cid-01JSHELL"}'
            ),
        ),
    )
    publish_events(1)
    page.wait_for_selector("#stream-message:not([hidden])", timeout=5000)
    assert "cid-01JSHELL" in page.locator("#stream-message").inner_text()

    # Twenty more envelopes, none of them an error: the id is still readable.
    publish_events(20)
    page.wait_for_timeout(800)
    assert "cid-01JSHELL" in page.locator("#stream-message").inner_text()

    page.locator("#stream-message-dismiss").click()
    # `state="attached"`: the node stays in the document and goes `hidden`, so
    # the default `visible` wait would time out on the very thing being proved.
    page.wait_for_selector("#stream-message[hidden]", state="attached", timeout=5000)
    assert page.locator("#stream-status").inner_text() in ("live", "reconnecting")
    assert all("400" in message for message in errors), errors


def test_the_shell_says_when_a_read_never_reaches_the_server(desktop) -> None:
    """**Defect 2 (HIGH)** at the second of the four modules that missed it.

    `app.js`'s `read()` awaited `response.json()` on a `fetch` that may reject,
    and nothing caught it. With `controld` stopped the page simply stopped
    updating: no sentence, no indicator change, an unhandled `Failed to fetch`
    on a console nobody has open.
    """
    page, errors = desktop
    page.route("**/api/fleet/tree", lambda route: route.abort("failed"))

    publish_events(1)

    page.wait_for_selector("#stream-message:not([hidden])", timeout=5000)
    assert "did not reach the server" in page.locator("#stream-message").inner_text()
    assert [error for error in errors if "pageerror" in error] == [], errors


def test_a_burst_of_envelopes_does_not_become_a_request_per_envelope(desktop) -> None:
    """**Defect 8 (LOW, and the one that scales).** QA measured 1/10/100
    envelopes producing 4/40/400 HTTP requests — perfectly linear, about 115
    requests a second from a single tab, against a store with one writer
    thread. Every envelope called `loadFleet()` (two reads) and
    `projects.reload()` (two more), with nothing in flight and nothing merged.

    The refresh is now coalesced: an envelope that arrives while a refresh is
    running marks it stale instead of starting a second one, so a burst of N
    costs two passes rather than N. The assertion is a **ceiling**, not a
    count — the exact number depends on where in a pass each envelope lands,
    and a test that pinned it would be pinning the scheduler.
    """
    page, errors = desktop
    seen: list[str] = []
    page.on(
        "request",
        lambda request: seen.append(request.url) if "/api/" in request.url else None,
    )

    publish_events(40)
    page.wait_for_timeout(1500)

    reads = [url for url in seen if "/api/events" not in url]
    assert len(reads) <= 16, (len(reads), reads[:20])
    # …and it really did refresh: a coalescer that dropped everything would
    # also pass the line above.
    assert len(reads) >= 2, reads
    assert errors == [], errors


# ==============================================================================
# QA run 3, D1 — the band between the two widths every gate used as bounds
# ==============================================================================

#: Anything a finger or a pointer can land on, inside one page root.
USABLE_CONTROLS = """
(root) => {
  const host = document.querySelector(root);
  if (host === null) return null;
  const out = [];
  for (const node of host.querySelectorAll("button, a[href], input, select, textarea")) {
    const box = node.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) {
      out.push(node.id || node.className || node.tagName);
    }
  }
  return out;
}
"""

#: The computed `display` of one selector, for a failure message that names the
#: cause rather than only the symptom.
DISPLAY_OF = """
(selector) => {
  const node = document.querySelector(selector);
  if (node === null) return "(absent)";
  return getComputedStyle(node).display;
}
"""


@contextmanager
def _at(
    client: Client,
    viewport: dict[str, int],
    *,
    touch: bool = False,
    init_script: str | None = None,
):
    """The shipped page at one viewport, torn down whatever happens."""
    play, browser, page, errors = _open(
        client, viewport, touch=touch, init_script=init_script
    )
    try:
        yield page, errors
    finally:
        browser.close()
        play.stop()


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
def test_both_two_pane_pages_can_be_navigated_at_every_declared_viewport(
    client: Client, master_doubles: MasterDoubles, viewport: str
) -> None:
    """QA run 3's D1: Projects and Settings lost their only navigation at 820.

    `app.css`'s `@media (max-width: 900px) { .herd-col { display: none } }` is
    the **Flock's** rule — its three panes are re-shown by
    `.herd[data-level] .col-*` — but `.herd-col` is also the class of the
    Projects list column and the Settings nav column, and the `.panes2` rescue
    that re-shows *those* lives inside `@media (max-width: 760px)`. So from
    761px to 900px inclusive both pages rendered a detail pane over an empty
    grid: zero usable controls on Projects with two projects in the store, and
    one on Settings — a back chevron whose target was the hidden column.

    Parametrised over `VIEWPORTS` and not over two hand-written widths, because
    the defect's whole cause of death was that the gates drove 390 and 1280 and
    the band sat between them. A width added to `render_check.VIEWPORTS` is
    driven here without this file being touched.
    """
    size = VIEWPORTS[viewport]
    with _at(client, size) as (page, errors):
        _nav(page, "projects")
        controls = page.evaluate(USABLE_CONTROLS, "#page-projects")
        display = page.evaluate(DISPLAY_OF, "#page-projects .herd-col")
        assert controls is not None, "#page-projects is not in the document"
        assert "proj-new" in controls, (
            f"projects at {size['width']}px: the list column computes"
            f" display:{display} and the page offers {len(controls)} usable"
            f" controls {controls} — 'New project' is not one of them"
        )

        _nav(page, "settings")
        items = page.locator("#page-settings .set-item:visible")
        display = page.evaluate(DISPLAY_OF, "#page-settings .herd-col")
        assert items.count() >= 2, (
            f"settings at {size['width']}px: the nav column computes"
            f" display:{display} and offers {items.count()} visible sections;"
            f" the page's usable controls are"
            f" {page.evaluate(USABLE_CONTROLS, '#page-settings')}"
        )

        # …and the navigation is not merely painted: the section it names opens.
        target = items.nth(1)
        title = target.inner_text().splitlines()[0].strip()
        target.click()
        page.wait_for_timeout(300)
        head = page.locator("#settings-panel .col-head")
        assert head.is_visible(), f"settings at {size['width']}px: the panel did not open"
        assert title.lower() in head.inner_text().lower(), (title, head.inner_text())

        # The way back, on exactly the widths that took one away. Below the
        # drill-down's breakpoint the panel replaced the list, so there must be
        # a chevron and it must restore the list; above it both panes are on
        # screen and a chevron would point at a column the reader is looking at.
        back = page.locator("#settings-back")
        if size["width"] <= 760:
            assert back.is_visible(), (
                f"settings at {size['width']}px: the panel replaced the nav column"
                " and there is no way back to it"
            )
            back.click()
            page.wait_for_timeout(300)
            assert page.locator("#page-settings .herd-col").is_visible(), (
                f"settings at {size['width']}px: the back chevron changed nothing"
            )
        else:
            assert not back.is_visible(), (
                f"settings at {size['width']}px: both panes are on screen and a"
                " back chevron is offered anyway — it sets data-level='list',"
                " which at this width changes nothing on the page"
            )

        assert errors == [], errors


# ==============================================================================
# QA run 3, D2 — a modal that opens where nothing is drawn
# ==============================================================================

#: What a tap at the middle of one element actually lands on.
HIT_TEST = """
(selector) => {
  const node = document.querySelector(selector);
  if (node === null) return null;
  const box = node.getBoundingClientRect();
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  return {
    width: box.width,
    height: box.height,
    display: getComputedStyle(node).display,
    landedOn: hit === null ? "(nothing)" : hit.id || hit.tagName,
    inADialog: hit !== null && hit.closest("dialog") !== null,
  };
}
"""


def _dialog_is_usable(page, dialog: str, control: str, width: int) -> None:
    """Both halves of "the modal opened": it is drawn, and taps reach it."""
    shown = page.evaluate(HIT_TEST, dialog)
    assert shown is not None, f"{dialog} is not in the document"
    assert shown["width"] > 0 and shown["height"] > 0, (
        f"{dialog} at {width}px: showModal() ran and the dialog computes"
        f" display:{shown['display']} at {shown['width']}x{shown['height']} —"
        " the modal is open, invisible, and its backdrop is swallowing every tap"
    )
    landed = page.evaluate(HIT_TEST, control)
    assert landed["inADialog"], (
        f"{control} at {width}px: a tap at its centre lands on"
        f" {landed['landedOn']}, not on the dialog"
        f" (box {landed['width']}x{landed['height']}, display {landed['display']})"
    )


def test_the_projects_dialogs_are_on_screen_on_a_phone(phone, store: Store) -> None:
    """QA run 3's D2, on the client the spec calls primary.

    `mountProjects()` builds `#dlg-project` and `#dlg-delete` inside
    `#page-projects` deliberately — `index.html`'s shell comment records why: a
    second copy at shell level would be the one `getElementById` handed back.
    The blanket `@media (max-width: 760px) { .panes2[data-level] > * { display:
    none } }` then hid them, and an author rule beats the UA's `dialog[open] {
    display: block }`. `showModal()` still ran: modal true, box 0x0, every tap
    on the page swallowed by the backdrop, no visible button anywhere in the
    dialog, and the only exit a keyboard Escape on a device with no keyboard.

    Both dialogs, because both are children of that root and a fix that reached
    one is a fix that reached half the defect. The assertion is a **hit test**
    and not `is_visible()`: what broke was where the taps went.
    """
    page, errors = phone
    seed(store)
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "projects")
    width = page.viewport_size["width"]

    page.locator("#proj-new").click()
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.getElementById('dlg-project').open") is True
    _dialog_is_usable(page, "#dlg-project", "#p-save", width)
    # …and it can be dismissed by a finger, which is the half Escape hid.
    page.locator("#dlg-project .dlg-acts .ghost").click()
    page.wait_for_timeout(200)
    assert page.evaluate("() => document.getElementById('dlg-project').open") is False

    page.locator('#proj-list .proj-row:not([data-reserved="true"])').first.click()
    page.wait_for_timeout(400)
    page.locator("#proj-delete").click()
    page.wait_for_timeout(400)
    assert page.evaluate("() => document.getElementById('dlg-delete').open") is True
    _dialog_is_usable(page, "#dlg-delete", "#dlg-delete-cancel", width)

    assert errors == [], errors


# ==============================================================================
# QA run 3, D3 — a tooltip left on screen that swallows the next click
# ==============================================================================

#: The tooltip's own box, and what a tap in the middle of it reaches.
TIP_HIT = """
() => {
  const tip = document.querySelector(".tip");
  if (tip === null) return null;
  const box = tip.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const hit = document.elementFromPoint(x, y);
  const info = document.querySelector(".legend-info");
  const infoBox = info === null ? null : info.getBoundingClientRect();
  const infoHit =
    infoBox === null
      ? null
      : document.elementFromPoint(
          infoBox.left + infoBox.width / 2,
          infoBox.top + infoBox.height / 2,
        );
  return {
    box: { top: box.top, left: box.left, width: box.width, height: box.height },
    landedOn: hit === null ? "(nothing)" : hit.className || hit.tagName,
    intercepts: hit !== null && (hit === tip || tip.contains(hit)),
    infoBlocked: infoHit !== null && (infoHit === tip || tip.contains(infoHit)),
  };
}
"""


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
def test_the_legend_tooltip_never_swallows_a_click(
    client: Client, master_doubles: MasterDoubles, viewport: str
) -> None:
    """QA run 3's D3, driven through the sequence that leaves the tip behind.

    `flock.js` binds `focus` → `showTip` on every legend key, and
    `<dialog>.close()` restores focus to the key that opened the sheet — so
    closing the bucket explainer re-fires `focus` and the tooltip comes back
    with no pointer anywhere near it. `.tip` was `position: fixed; z-index: 40`
    with pointer events on, so a 19rem box sat over the page eating taps: two
    controls at 1280 and four at 390, including `.legend-info`, which is U1's
    documented way into that same explainer.

    The assertion is over the tooltip's **own box** rather than a named control,
    because which controls it covers depends on what is seeded and how wide the
    page is; what is always true is that a tooltip must never be what a tap
    lands on.
    """
    size = VIEWPORTS[viewport]
    with _at(client, size) as (page, errors):
        _nav(page, "flock")
        key = page.locator("#flock-legend .legend-key").first
        key.hover()
        page.wait_for_timeout(150)
        key.click()
        page.wait_for_timeout(300)
        assert page.evaluate("() => document.getElementById('dlg-legend').open") is True
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        assert page.evaluate("() => document.getElementById('dlg-legend').open") is False

        reading = page.evaluate(TIP_HIT)
        if reading is None:
            # The sheet's close did not bring the tooltip back at this width —
            # then there is nothing for it to swallow. Reported, not assumed.
            return
        assert not reading["intercepts"], (
            f"the legend tooltip at {size['width']}px is still on screen after the"
            f" sheet closed, and a tap at its centre lands on {reading['landedOn']}:"
            f" every tap inside {reading['box']} is swallowed"
        )
        assert not reading["infoBlocked"], (
            f"the legend tooltip at {size['width']}px covers `.legend-info` — U1's"
            " documented way into the explainer — and takes the tap"
        )
        # The other half of the story the fix tells: the tip goes when the key
        # it belongs to stops being focused, which is what the tap that now
        # reaches the control underneath does.
        page.evaluate("() => document.activeElement.blur()")
        page.wait_for_timeout(150)
        assert page.locator(".tip").count() == 0, "the tooltip outlived the focus it follows"
        assert errors == [], errors


# ==============================================================================
# QA run 4, lane A — the phone defects: D4, D5, D8 and D9
# ==============================================================================


def _tap(page, selector: str) -> bool:
    """A real finger on the centre of `selector`. False if it is not there.

    `locator.click()` is a mouse; this is the touchscreen. The distinction is
    the whole of D4: a `<dialog>` with no `closedby` does not close on a
    backdrop *tap*, and a mouse click is not the event a phone sends.
    """
    box = page.evaluate(
        """(s) => { const e = document.querySelector(s);
             if (e === null) return null;
             const b = e.getBoundingClientRect();
             if (b.width === 0 && b.height === 0) return null;
             return [Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2)]; }""",
        selector,
    )
    if box is None:
        return False
    page.touchscreen.tap(box[0], box[1])
    page.wait_for_timeout(350)
    return True


#: Everything a reader with no keyboard could use to get out of a `<dialog>`,
#: read off the live element rather than off the markup: whether it is open and
#: modal, every button of its own that has a box, whether that button is wired
#: to close it, and whether the platform's own light-dismiss is asked for.
DIALOG_EXITS = """
(id) => {
  const d = document.getElementById(id);
  if (d === null) return null;
  const visible = [...d.querySelectorAll('button')].filter((e) => {
    const b = e.getBoundingClientRect();
    return b.width > 0 && b.height > 0;
  });
  return {
    open: d.open,
    modal: d.matches(':modal'),
    closedby: d.getAttribute('closedby'),
    closedbySupported: 'closedBy' in d,
    dataCloseWired: document.querySelectorAll('[data-close="' + id + '"]').length,
    visibleButtons: visible.map((e) => ({
      id: e.id || null,
      text: (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 32),
      w: Math.round(e.getBoundingClientRect().width),
      h: Math.round(e.getBoundingClientRect().height),
      closesThisDialog: e.getAttribute('data-close') === id,
    })),
  };
}
"""


def test_the_legend_sheet_is_dismissable_by_touch_alone(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """QA run 4's D4: the explainer sheet was a trapdoor on a phone.

    `index.html` declared `<dialog id="dlg-legend" class="sheet">` with **no
    button at all**, while `flock.js` looped over `[data-close="dlg-legend"]`
    to wire a close handler — an attribute that existed nowhere in the
    document, so the loop was dead code and `dataCloseWired` read 0. A native
    `<dialog>` with no `closedby` does not light-dismiss, so the sheet had
    exactly one exit: a keyboard `Escape`. The sheet opens from the ⓘ **and
    from all eight legend keys**, which makes the whole legend row a trapdoor
    whose only phone exit is a page reload.

    This is run 3's D2 one layer over. That sweep marked `#dlg-legend` fine
    because it measured **visibility**; this one measures **dismissal**, and
    it measures it with a finger rather than a synthesised mouse.
    """
    with _at(client, PHONE, touch=True) as (page, errors):
        _nav(page, "flock")
        # The trapdoor's own door: a legend key, not the ⓘ. Eight of them open
        # this sheet and QA measured the phone entering through one.
        assert _tap(page, "#flock-legend .legend-key"), "no legend key at 390px"
        reading = page.evaluate(DIALOG_EXITS, "dlg-legend")
        assert reading is not None and reading["open"] is True, reading

        exits = [b for b in reading["visibleButtons"] if b["closesThisDialog"]]
        assert exits, (
            "the legend sheet is open and modal at 390px and offers no visible"
            f" control that closes it: visibleButtons={reading['visibleButtons']},"
            f" dataCloseWired={reading['dataCloseWired']},"
            f" closedby={reading['closedby']!r} — on a phone the only exit is a"
            " page reload"
        )
        small = [b for b in exits if min(b["w"], b["h"]) < 24]
        assert not small, f"the sheet's way out is below 24x24: {small}"

        # …and it is not merely present: a finger on it closes the sheet.
        assert _tap(page, '#dlg-legend [data-close="dlg-legend"]')
        assert page.evaluate("() => document.getElementById('dlg-legend').open") is False, (
            "tapping the sheet's own close control left it open"
        )

        # The platform's light-dismiss, asked for and honoured. Verified rather
        # than assumed (chromium 153 here): a tap on the backdrop, far from the
        # box, with the button deliberately not used.
        assert _tap(page, "#flock-legend .legend-info")
        again = page.evaluate(DIALOG_EXITS, "dlg-legend")
        assert again["open"] is True, again
        assert again["closedbySupported"] is True, (
            "this browser has no `closedby`, so the attribute in the markup is"
            " decoration; the close button above is what the fix rests on"
        )
        page.touchscreen.tap(6, 6)
        page.wait_for_timeout(350)
        assert page.evaluate("() => document.getElementById('dlg-legend').open") is False, (
            "a tap on the backdrop left the sheet open although the element"
            f" declares closedby={again['closedby']!r}"
        )
        assert errors == [], errors


#: Wraps `addEventListener` before a single module of the page has run, and
#: counts per element per type. A `WeakMap` because the count belongs to the
#: node and must not keep it alive.
LISTENER_SPY = r"""
(() => {
  window.__clickSpy = new WeakMap();
  const original = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    try {
      if (this instanceof Element || this === document || this === window) {
        let counts = window.__clickSpy.get(this);
        if (!counts) { counts = {}; window.__clickSpy.set(this, counts); }
        counts[type] = (counts[type] || 0) + 1;
      }
    } catch (error) { /* a spy that breaks the page proves nothing */ }
    return original.call(this, type, fn, opts);
  };
})();
"""

#: How many click handlers one tap on `selector` runs: its own, plus every
#: delegated one on an ancestor, since a click bubbles.
CLICK_HANDLERS = """
(selector) => {
  const el = document.querySelector(selector);
  if (el === null) return null;
  let total = 0;
  const chain = [];
  let node = el;
  while (node) {
    const counts = window.__clickSpy.get(node);
    const n = counts && counts.click ? counts.click : 0;
    if (n) {
      chain.push((node.tagName + (node.id ? '#' + node.id : '')) + ' x' + n);
      total += n;
    }
    node = node.parentElement;
  }
  return { total, chain };
}
"""

#: The spy proved in both directions before it is believed: a planted node with
#: a known number of handlers must read back as that number. A spy that counted
#: nothing would report every control as clean.
SPY_PROOF = """
() => {
  const host = document.createElement('div');
  const button = document.createElement('button');
  host.appendChild(button);
  document.body.appendChild(host);
  button.addEventListener('click', () => {});
  button.addEventListener('click', () => {});
  host.addEventListener('click', () => {});
  let total = 0;
  let node = button;
  while (node) {
    const counts = window.__clickSpy.get(node);
    total += counts && counts.click ? counts.click : 0;
    node = node.parentElement;
  }
  host.remove();
  return total;
}
"""


def test_one_tap_on_a_session_card_runs_exactly_one_handler(
    client: Client, master_doubles: MasterDoubles, store: Store
) -> None:
    """QA run 4's D5: one click on a card ran the open twice.

    Two bindings for one click — `flock.js` bound the card itself, and
    `app.js` carries the delegated listener on `#flock-cards` that
    `index.html` documents as the intended path. Measured 6/6 deterministic
    across all four cards: two WebSocket sockets, two `GET /api/sessions/{id}`,
    two degrade lines and one console warning per click; at the `Runner` seam
    `['snapshot', 'attach', 'snapshot', 'attach']`, which in production is two
    `capture-pane` and two `pipe-pane` against the same tmux pane.
    `session.js::closeAttached()` is why it read as a warning and not a crash.

    The redundant half is the card's own listener: `index.html` documents the
    delegated one, so that is the one that stays.
    """
    session = seed(store)
    with _at(client, DESKTOP, init_script=LISTENER_SPY) as (page, errors):
        _nav(page, "flock")
        page.reload()
        page.wait_for_timeout(700)
        _nav(page, "flock")

        assert page.evaluate(SPY_PROOF) == 3, (
            "the listener spy does not count: a planted node with two of its own"
            " click handlers and one on its parent did not read back as three,"
            " so any count it reports below is meaningless"
        )

        page.locator("#flock-projects .project").first.click()
        page.wait_for_timeout(300)
        selector = f'#flock-cards .card[data-session-id="{session.id}"]'
        assert page.locator(selector).count() == 1, page.locator("#flock-cards").inner_html()

        reading = page.evaluate(CLICK_HANDLERS, selector)
        assert reading is not None, selector
        assert reading["total"] == 1, (
            "one tap on a session card runs"
            f" {reading['total']} click handlers, not one: {reading['chain']} —"
            " the card is opened twice, which is two attaches against the same"
            " tmux pane"
        )
        assert errors == [], errors


#: Every control the reader can reach on the page that is open, with the shape
#: WCAG 2.2 AA 2.5.8 asks about. Padding is already inside the border box, so
#: the box **is** the target.
TOUCH_TARGETS = r"""
() => {
  const root = document.querySelector('[id^="page-"]:not([hidden])');
  if (root === null) return null;
  const selector =
    'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  return [...root.querySelectorAll(selector)]
    .filter((e) => {
      const b = e.getBoundingClientRect();
      return b.width > 0 && b.height > 0;
    })
    .map((e) => {
      const b = e.getBoundingClientRect();
      return {
        key: e.id || e.className.toString().trim().split(/\s+/).slice(0, 2).join('.'),
        text: (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 24),
        w: Math.round(b.width),
        h: Math.round(b.height),
        minSide: Math.round(Math.min(b.width, b.height)),
      };
    });
}
"""

#: A back chevron's own box against the box of the band it sits in. A chevron
#: that took the whole band is D8: `place-items: center` then puts the glyph at
#: the middle of the screen with nothing beside it.
CHEVRON_SHAPE = """
(selector) => {
  const el = document.querySelector(selector);
  if (el === null) return null;
  const parent = el.parentElement;
  const b = el.getBoundingClientRect();
  const p = parent.getBoundingClientRect();
  return {
    parent: parent.tagName + '.' + parent.className.toString().trim(),
    w: Math.round(b.width),
    h: Math.round(b.height),
    leadingGap: Math.round(b.left - p.left),
    parentWidth: Math.round(p.width),
    glyphCentre: Math.round(b.left + b.width / 2),
  };
}
"""

#: The drill-downs, by the route a phone takes to reach them. The back chevrons
#: are `display: none` above 760, which is why run 4's 1280 sweep saw not one
#: sub-24 target and this is driven at 390 only.
DRILL_DOWNS = (
    ("projects", "#page-projects .proj-row"),
    ("settings", "#page-settings .set-item"),
    ("flock", "#page-flock .col-projects .project"),
)


def test_every_control_at_phone_width_meets_the_target_size_minimum(
    client: Client, master_doubles: MasterDoubles, store: Store
) -> None:
    """QA run 4's D9, and D8 with it: six controls below 24x24 at 390px.

    WCAG 2.2 AA 2.5.8. Every one of the six was 21px tall, and the two shapes
    share one cause — `.back` was `display: grid; place-items: center` with no
    size of its own, so its box was whatever the parent imposed. Driven at 390
    and through **both** drill-down levels, because the chevrons are
    `display: none` above 760 and the 1280 sweep could not see them.
    """
    seed(store)
    with _at(client, PHONE, touch=True) as (page, errors):
        page.reload()
        page.wait_for_timeout(700)
        small: list[str] = []
        for target, into in DRILL_DOWNS:
            _nav(page, target)
            for level in ("list", "detail"):
                if level == "detail":
                    if page.locator(into).count() == 0:
                        continue
                    page.locator(into).first.click()
                    page.wait_for_timeout(400)
                for control in page.evaluate(TOUCH_TARGETS) or []:
                    if control["minSide"] < 24:
                        small.append(
                            f"{target}/{level} {control['w']}x{control['h']}"
                            f" {control['key']} {control['text']!r}"
                        )
        assert small == [], (
            "controls below WCAG 2.2 AA 2.5.8's 24x24 minimum at 390px, where a"
            f" chevron is the only way out of a drill-down: {small}"
        )
        assert errors == [], errors


def test_the_settings_back_chevron_is_a_chevron_and_not_a_full_width_band(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """QA run 4's D8: `#settings-back` was 394x21 with its glyph at x=193.

    `.back` had `display: grid; place-items: center` and no width, so its shape
    was the parent's. Projects (`DIV.proj-band`, a flex **row**) gave it 21x21
    at the leading edge; Settings (`DIV.proj-detail set-panel`, a flex
    **column**) stretched it to the full 394px and `place-items: center` put
    the chevron at the dead centre of a 390px screen with nothing beside it —
    a glyph that looks like a heading ornament rather than the way back.

    Pre-existing, and not introduced by the D1 fix. The assertion is the
    comparison QA made against the same control on a page whose band is a row.
    """
    with _at(client, PHONE) as (page, errors):
        _nav(page, "settings")
        page.locator("#page-settings .set-item").first.click()
        page.wait_for_timeout(400)
        shape = page.evaluate(CHEVRON_SHAPE, "#settings-back")
        assert shape is not None, "#settings-back is not in the document"
        assert shape["w"] < shape["parentWidth"] / 2, (
            f"#settings-back is {shape['w']}x{shape['h']} inside a"
            f" {shape['parentWidth']}px {shape['parent']} — a full-width band,"
            f" and `place-items: center` puts its chevron at x={shape['glyphCentre']}"
            " with nothing beside it"
        )
        assert shape["leadingGap"] <= 12, (
            f"#settings-back sits {shape['leadingGap']}px in from the leading edge"
            " of its band; every other back chevron leads its row"
        )
        assert errors == [], errors


# ----- DUP-1: the session pane belongs to the last card ASKED FOR -------------
#
# BC-1's sibling, one file over. `openSession()` writes `view.sessionId` and
# paints **after** its await with no guard, and both of its callers — the
# delegated card listener and the Projects page's session anchor — start it
# without awaiting. So two taps in quick succession leave two reads in flight
# and the pane settles on whichever one *resolved* last, which is not
# necessarily the one the reader asked for last.
#
# It was named by BC-1's investigation and never reproduced. The test below
# reproduces it, deterministically, at the shipped seam: the older read is
# parked and released only after the newer card has already painted, which is
# the losing interleaving pinned at 100% rather than hoped for.


def _two_cards(store: Store) -> tuple[Session, Session]:
    """Two sessions under one project, told apart by their titles.

    One project, because the cards have to be on screen **together**: the
    second pane lists the open project's sessions, so a race between two
    projects' cards would be a race the reader cannot run.
    """
    project = store.create_project(name="shepherd", description=None)
    rows = []
    for engine_id, title in (
        ("eng-older", "the read that was asked for first"),
        ("eng-newer", "the read that was asked for last"),
    ):
        row = store.register_session(
            engine_session_id=engine_id,
            workspace_id=project.id,
            repo_id=None,
            cwd="/root/Shepherd",
            started_at="2026-09-16T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        store.apply_title(row.id, title, "engine")
        rows.append(row)
    return rows[0], rows[1]


def test_a_session_read_that_resolves_after_a_newer_card_paints_nothing(
    desktop, store: Store
) -> None:
    """Two taps, and the pane keeps the one that was asked for last.

    The assertions are the pane's title **and** the card's `aria-current`,
    because they come from two different writes — `renderSession(answer.session)`
    paints the pane and `view.sessionId` is what `flock.js` marks the card
    from. A fix that guarded only the paint would leave the Flock claiming a
    different session is open than the one on screen, so both are read.
    """
    page, errors = desktop
    older, newer = _two_cards(store)
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "flock")
    page.locator("#flock-projects .project").first.click()
    page.wait_for_timeout(300)

    # Park the older card's detail read, and only it: `/api/fleet` and
    # `/api/fleet/tree` keep flowing, so the page behaves in every other way.
    hold_fetches(page, f"/api/sessions/{older.id}$")

    page.locator(f'#flock-cards .card[data-session-id="{older.id}"]').click()
    page.wait_for_function("() => window.__held.length === 1", timeout=5000)
    page.locator(f'#flock-cards .card[data-session-id="{newer.id}"]').click()
    page.wait_for_selector(
        '#session-title:text-is("the read that was asked for last")', timeout=5000
    )

    assert page.evaluate("() => window.__release()") == 1
    page.wait_for_function("() => window.__delivered === 1", timeout=5000)
    # The stale answer is now in the page's hands. The assertions below are
    # negative — that it changed nothing — so they need a point after which it
    # can no longer act: the body is local and already buffered, and one
    # `requestAnimationFrame` plus a beat is past every microtask it queues.
    page.wait_for_timeout(500)

    assert (
        page.locator("#session-title").inner_text()
        == "the read that was asked for last"
    )
    assert (
        page.locator(f'#flock-cards .card[data-session-id="{newer.id}"]').get_attribute(
            "aria-current"
        )
        == "true"
    )
    assert (
        page.locator(f'#flock-cards .card[data-session-id="{older.id}"]').get_attribute(
            "aria-current"
        )
        == "false"
    )
    assert errors == [], errors


def test_a_session_read_parked_by_a_card_cannot_take_the_pane_from_a_link(
    desktop, store: Store
) -> None:
    """The same race across the shell's **other** unawaited caller.

    `openSession` has two call sites and neither awaits: the delegated card
    listener on `#flock-cards`, and the `[data-page]` anchor the Projects page
    builds, which the shell honours by showing the Flock and opening the
    session the link names. A guard that lived in the card listener would leave
    this red, which is what makes this the variant worth driving: the two reads
    are started by two different controls on two different pages.
    """
    page, errors = desktop
    older, newer = _two_cards(store)
    page.reload()
    page.wait_for_timeout(700)
    _nav(page, "flock")
    page.locator("#flock-projects .project").first.click()
    page.wait_for_timeout(300)

    hold_fetches(page, f"/api/sessions/{older.id}$")

    page.locator(f'#flock-cards .card[data-session-id="{older.id}"]').click()
    page.wait_for_function("() => window.__held.length === 1", timeout=5000)

    _nav(page, "projects")
    page.locator("#proj-list .proj-row").first.click()
    page.wait_for_timeout(400)
    link = page.locator(f'#proj-detail .mini-open[data-session-id="{newer.id}"]')
    assert link.count() == 1, page.locator("#proj-detail").inner_html()
    link.click()
    page.wait_for_selector(
        '#session-title:text-is("the read that was asked for last")', timeout=5000
    )

    assert page.evaluate("() => window.__release()") == 1
    page.wait_for_function("() => window.__delivered === 1", timeout=5000)
    page.wait_for_timeout(500)

    assert page.locator("#page-flock").is_visible()
    assert (
        page.locator("#session-title").inner_text()
        == "the read that was asked for last"
    )
    assert errors == [], errors
