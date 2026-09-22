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

from web.conftest import Client, MasterDoubles, seed
from web.test_shell import render_check_constant

from shepherd.store.db import Store

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


def _open(client: Client, viewport: dict[str, int]):
    """A chromium page on the shipped index, with its console collected."""
    from playwright.sync_api import sync_playwright

    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
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
def _at(client: Client, viewport: dict[str, int]):
    """The shipped page at one viewport, torn down whatever happens."""
    play, browser, page, errors = _open(client, viewport)
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
