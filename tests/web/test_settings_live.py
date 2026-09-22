"""T7 — the two pages driven in a real browser against the real server.

**Why this exists beside the static scans.** Every other module in `tests/web/`
asserts on bytes: the shipped JS parsed and never executed, plus HTTP through
`invoke()`. That seam cannot see the thing D25 is actually about — *what a
person looking at the page can read*. `args` absent from a scan of `settings.js`
is a strong signal; `args` absent from the pixels, with a real record on disk
that contains a real secret, is the property.

**What is real here, named because that is the whole claim.** The server is the
shipped `ThreadingHTTPServer` on a loopback port. The routes are the shipped
route table resolving to registered tools through the shipped `invoke()`. The
audit record is written by the shipped `build_audit_sink` into the shipped
`RotatingJsonlLog` and read back by the shipped `read_audit_records`. The
modules are fetched from `/static/` by the real server. The browser is chromium.
The only thing this test supplies is the **shell**, served from the committed
`fixtures/shell_harness.html` at the server's own origin — because `index.html`
belongs to Phase 5 and is rewritten in a worktree of its own.

**The mount order is the shell's, not a convenient one.** `#page-settings`
ships `hidden` and `app.js` reveals a page after mounting it, so the mount here
happens while the root is hidden and the reveal comes after. A module that
measured anything at mount time would work in a test that revealed first and
fail in the product.

Skipped, not failed, where chromium is absent: a browser that is not installed
is an environment fact, and reporting it as a code defect is the failure mode
`ENVIRONMENT not code` names.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from web.conftest import Client, MasterDoubles

from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.toolsurface.audit import AUDIT_PREFIX, build_audit_sink
from shepherd.toolsurface.types import ActorKind, AuditRecord, BlastClass

playwright_api = pytest.importorskip("playwright.sync_api")

HARNESS = Path(__file__).resolve().parent / "fixtures" / "shell_harness.html"

#: Planted in a real record's `args` and asserted **absent from the pixels**.
#: It is not secret-shaped on purpose: `redact_args` already masks anything
#: whose key looks like a credential, so a value it would have masked proves
#: nothing about the page's own whitelist. This one survives redaction and is
#: excluded only because the page never reads `args` at all (D25).
PLANTED = "the-target-path-nobody-should-see"

MOUNT = """
async (urls) => {
  const chat = await import(urls.chat);
  const settings = await import(urls.settings);
  // The shell's own order: mount while the root is still hidden, then reveal,
  // then read. `app.js` lands on Shepherd from a document whose visible root is
  // the Flock, so nothing may depend on being visible at mount time.
  chat.mountShepherd();
  settings.mountSettings();
  document.getElementById("page-flock").hidden = true;
  document.getElementById("page-settings").hidden = false;
  await settings.loadSettings();
  await chat.loadShepherd();
  return true;
}
"""


def _record(at: str, tool: str, decision: str) -> AuditRecord:
    return AuditRecord(
        at=at,
        correlation_id="c-1",
        actor_kind=ActorKind.HUMAN,
        actor_id="web",
        tool=tool,
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        args={"target": PLANTED},
        autonomy_level=2,
        decision=decision,
        approved_by="user",
        approval_id="ap-1",
        result="ok",
        failure=None,
        duration_ms=3,
    )


def _plant_audit(root: Path) -> None:
    """Two real records, through the shipped writer — not a hand-written file."""
    sink = build_audit_sink(
        log=RotatingJsonlLog(root, AUDIT_PREFIX),
        bump=lambda kind: pytest.fail(f"the audit line was lost: {kind}"),
        date_of=lambda at: at[:10],
    )
    sink(_record("2026-09-16T10:00:30Z", "spawn_session", "allow"))
    sink(_record("2026-09-16T10:00:31Z", "kill_session", "deny"))


def _harness_at(origin: str) -> str:
    """The committed harness, with its two relative asset paths served-relative.

    The file links `../../../src/shepherd/web/static/app.css` so it can be
    opened from disk by `tools/render_check.py`; at an origin that path is a
    404. Only the prefix is rewritten — the bytes under test are the committed
    ones, and the rewrite is asserted to have changed something.
    """
    markup = HARNESS.read_text(encoding="utf-8")
    served = markup.replace("../../../src/shepherd/web/static/", "/static/")
    assert served != markup, "the harness no longer links the stylesheet relatively"
    assert origin  # the origin is the browser's; the markup carries no absolute URL
    return served


@pytest.fixture()
def browser_page(client: Client):
    """A chromium page whose only non-server bytes are the committed harness."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
            pytest.skip(f"chromium is not available: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on(
            "console",
            lambda message: errors.append(f"{message.type}: {message.text}")
            if message.type == "error"
            else None,
        )
        page.route(
            f"{client.origin}/__shell__",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=_harness_at(client.origin),
            ),
        )
        page.goto(f"{client.origin}/__shell__")
        page.evaluate(
            MOUNT,
            {
                "chat": f"{client.origin}/static/chat.js",
                "settings": f"{client.origin}/static/settings.js",
            },
        )
        page.wait_for_timeout(200)
        yield page, errors
        browser.close()


def test_the_shell_and_the_two_modules_load_from_the_real_server(
    browser_page, master_doubles: MasterDoubles
) -> None:
    """Arrival: the modules came off the socket and neither threw.

    A page that never loaded a module passes every absence assertion below, so
    the presence of both is asserted first and the console is asserted empty.
    """
    page, errors = browser_page
    assert errors == [], errors
    assert page.locator("#settings-nav .set-item").count() == 10
    assert page.locator("#page-settings").is_visible()
    # …and the mount ran while the root was hidden, which is the shell's order.
    assert page.locator("#shepherd-input").count() == 1


@pytest.mark.parametrize("planted", [PLANTED])
def test_the_audit_tail_shows_four_fields_of_a_real_record_and_never_its_args(
    browser_page, master_doubles: MasterDoubles, planted: str
) -> None:
    """D25, end to end: a real record with a real argument, and the pixels.

    The record is written by the shipped sink, read by the shipped reader,
    served by the shipped route and rendered by the shipped module. The
    argument is asserted **present on the wire** and **absent from the page** —
    one without the other is either a vacuous exclusion or an unexplained gap.
    """
    page, errors = browser_page
    _plant_audit(master_doubles.audit_root)

    # Arrival on the wire: the route really carries the record, and the record
    # really carries the argument the page must not print.
    wire = page.evaluate(
        "async () => (await (await fetch('/api/audit')).json())",
    )
    assert wire["ok"] is True, wire
    records = wire["data"]["records"]
    assert len(records) == 2, records
    assert any(planted in json.dumps(row) for row in records), records

    # Re-read the page with the record in place. This is a click, not a timer:
    # the tail is read on the first paint, and re-opening Settings is the
    # affordance a person has.
    page.evaluate(
        "async (url) => { const m = await import(url); await m.loadSettings(); }",
        f"{page.url.rsplit('/', 1)[0]}/static/settings.js",
    )
    page.locator("#settings-nav .set-item", has_text="Data").click()
    page.wait_for_timeout(150)

    rows = page.locator("#settings-panel .audit .audit-row")
    assert rows.count() == 2, rows.all_inner_texts()
    for index in range(2):
        assert rows.nth(index).locator("span").count() == 4, index

    painted = page.locator("#settings-panel").inner_text()
    assert planted not in painted, painted
    assert "args" not in painted.lower(), painted
    # …and the four that are shown really are shown.
    assert "kill_session" in painted and "spawn_session" in painted, painted
    assert "user" in painted, painted
    # A denied call is not painted as an allowed one.
    assert page.locator("#settings-panel .audit-no").count() == 1
    assert page.locator("#settings-panel .audit-yes").count() == 1
    assert errors == [], errors


def test_the_autonomy_write_goes_through_the_real_route(
    browser_page, client: Client
) -> None:
    """D65's control, clicked in a browser, landing in the real policy state.

    The level is read from the server before and after, so a control that
    re-rendered itself without writing anything — the optimistic render — fails
    here even though the page would look right.
    """
    page, errors = browser_page
    assert client.request("/api/autonomy").json()["data"] == {"level": 2}

    page.locator("#settings-nav .set-item", has_text="Autonomy").click()
    page.wait_for_timeout(120)
    options = page.locator("#settings-panel .opt")
    assert options.count() == 2, options.all_inner_texts()
    assert page.locator('#settings-panel .opt[aria-pressed="true"]').inner_text() == (
        "Ask me before anything leaves this machine"
    )

    options.nth(1).click()
    page.wait_for_timeout(200)

    assert client.request("/api/autonomy").json()["data"] == {"level": 3}
    assert page.locator('#settings-panel .opt[aria-pressed="true"]').inner_text() == (
        "Approve automatically"
    )
    # U12: still no number anywhere in the panel, after the write.
    panel = page.locator("#settings-panel").inner_text()
    assert not any(character.isdigit() for character in panel), panel
    assert errors == [], errors


def test_a_turn_posted_from_the_composer_reaches_master_send(
    browser_page, master_doubles: MasterDoubles
) -> None:
    """The composer, over the real socket — and the turn id comes back."""
    page, errors = browser_page
    page.evaluate(
        "() => { document.getElementById('page-settings').hidden = true;"
        " document.getElementById('page-shepherd').hidden = false; }"
    )
    page.fill("#shepherd-input", "what's blocked?")
    page.click("#shepherd-send")
    page.wait_for_timeout(250)

    assert master_doubles.sent == ["what's blocked?"]
    assert page.locator("#shepherd-thread .turn-you .bubble").last.inner_text() == (
        "what's blocked?"
    )
    assert page.locator("#shepherd-status").inner_text() == "turn-01JCHAT"
    assert page.locator("#shepherd-input").input_value() == ""
    assert errors == [], errors


def test_no_element_the_modules_build_claims_a_page_root(browser_page) -> None:
    """`PAGE_ROOT_SELECTOR` is `[id^="page-"]`, so an id is a claim.

    The prototype's topbar heading is `id="page-title"`; copied into a page it
    becomes a seventh, permanently-visible page root and
    `tools/render_check.py` reports *"7 page roots visible at once"* on every
    page — a routing failure with nothing to do with routing. This asserts the
    count **after** both modules have rendered every panel, because the ids a
    module adds are the ones a static read of the shell cannot see.
    """
    page, errors = browser_page
    for index in range(10):
        page.locator("#settings-nav .set-item").nth(index).click()
        page.wait_for_timeout(40)

    roots = page.evaluate("() => [...document.querySelectorAll('[id^=\"page-\"]')].map(e => e.id)")
    assert sorted(roots) == [
        "page-flock",
        "page-kanban",
        "page-projects",
        "page-queues",
        "page-settings",
        "page-shepherd",
    ], roots
    assert errors == [], errors


def test_the_harness_served_here_is_the_committed_one() -> None:
    """The only bytes this module supplies are the fixture's, minus a prefix.

    Without this, the rewrite above is an unbounded edit: a test that patched
    the markup while serving it would be proving a page that does not exist.
    """
    served = _harness_at("http://127.0.0.1:1")
    original = HARNESS.read_text(encoding="utf-8")
    assert len(re.findall(r"id=\"page-[a-z]+\"", served)) == 6, served
    assert served == original.replace("../../../src/shepherd/web/static/", "/static/")
