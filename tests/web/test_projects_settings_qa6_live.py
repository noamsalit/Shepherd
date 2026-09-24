"""qa6 P13 — BC-12 R2/R4/R5, BC-18 (Projects), BC-24, on the shipped page.

Each test is one of qa6's failing scenarios reduced to its root cause and driven
in chromium against the **shipped** `index.html`, served with its modules by
the real `ThreadingHTTPServer` on a loopback port, over a real store behind the
real route table. The stream is real too: a project mutation made by a second
client (`Client.post`) reaches the page over `/api/events`, which is what makes
`app.js` re-read the Projects list — the rebuild BC-18 and R5 are about.

**Network timing is the only thing the test bends**, and it is bent in one
place: `SHIM` wraps `window.fetch` for URLs matching a pattern, parks the next
`holdNext` of them until `__releaseHeld()`, and counts every matched reply whose
body the page has *finished handling* (`consumed`). That count is the settle
signal: it is bumped in a task queued after the body resolved, so every
microtask continuation of the product's `await` — the paint included — has run
before it moves. No test here waits on a duration.

Skipped, not failed, where chromium is absent (an environment fact).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from web.conftest import Client, MasterDoubles

from shepherd.store.db import Store

playwright_api = pytest.importorskip("playwright.sync_api")

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route, ViewportSize

DESKTOP_WIDTH, DESKTOP_HEIGHT = 1280, 900

ASK = "Ask me before anything leaves this machine"
AUTO = "Approve automatically"

#: `settings.js`'s sentence for a rejected fetch, spelled here as the oracle.
SETTINGS_UNREACHABLE = (
    "The request did not reach the server — Shepherd may not be running, so "
    "these numbers are whatever was last read."
)

#: A refusal envelope in the product's own shape (`{ok, data, error,
#: correlation_id}`), answered in the page by `page.route`.
def refused(correlation_id: str) -> str:
    return json.dumps(
        {"ok": False, "data": None, "error": "request failed", "correlation_id": correlation_id}
    )


SHIM = """(pattern) => {
  const real = window.fetch;
  const expression = new RegExp(pattern);
  const shim = { holdNext: 0, held: [], sent: 0, consumed: 0 };
  window.__shim = shim;
  const track = (response) => {
    const json = response.json.bind(response);
    response.json = () => json().then((body) => {
      setTimeout(() => { shim.consumed += 1; }, 0);
      return body;
    });
    return response;
  };
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!expression.test(url)) {
      return real.call(window, input, init);
    }
    const send = () => {
      shim.sent += 1;
      return real.call(window, input, init).then(track);
    };
    if (shim.holdNext > 0) {
      shim.holdNext -= 1;
      return new Promise((resolve, reject) => {
        shim.held.push(() => send().then(resolve, reject));
      });
    }
    return send();
  };
  window.__releaseHeld = () => {
    const queued = shim.held.splice(0, shim.held.length);
    for (const go of queued) { go(); }
    return queued.length;
  };
}"""


def install_shim(page: Page, pattern: str, hold: int) -> None:
    page.evaluate(SHIM, pattern)
    page.evaluate("(n) => { window.__shim.holdNext = n; }", hold)


def eventually(page: Page, predicate: str, arg: object = None, timeout: float = 3000) -> bool:
    """A bounded wait on a DOM predicate, answered as a value for the assert."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.wait_for_function(predicate, arg=arg, timeout=timeout)
    except PlaywrightTimeout:
        return False
    return True


class Shipped:
    """The shipped page and what it said on the console."""

    def __init__(self, page: Page, errors: list[str], page_errors: list[str]) -> None:
        self.page = page
        self.errors = errors
        self.page_errors = page_errors


@pytest.fixture()
def shipped(client: Client, master_doubles: MasterDoubles) -> Iterator[Shipped]:
    from playwright.sync_api import sync_playwright

    play = sync_playwright().start()
    try:
        browser = play.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()
        pytest.skip(f"chromium is not available: {exc}")
    try:
        viewport: ViewportSize = {"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT}
        page = browser.new_page(viewport=viewport)
        page.set_default_timeout(5000)
        errors: list[str] = []
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(f"pageerror: {error}"))
        page.on(
            "console",
            lambda message: errors.append(f"{message.type}: {message.text}")
            if message.type == "error"
            else None,
        )
        page.goto(f"{client.origin}/")
        page.wait_for_function(
            "() => document.getElementById('stream-status').textContent === 'live'"
        )
        yield Shipped(page, errors, page_errors)
    finally:
        browser.close()
        play.stop()


def open_projects(page: Page) -> None:
    page.locator('.nav-item[data-page="projects"]').click()
    page.wait_for_selector("#proj-list .proj-row")


def open_row(page: Page, project_id: str, name: str) -> None:
    page.locator(f'#proj-list .proj-row[data-project-id="{project_id}"]').click()
    page.wait_for_selector(f'#proj-detail .proj-title:text-is("{name}")')


def open_edit(page: Page) -> None:
    page.locator("#proj-edit").click()
    page.wait_for_selector("#dlg-project[open]")


def dialog_paths(page: Page) -> list[str]:
    texts = page.locator("#p-paths .path .path-text").all_text_contents()
    return sorted(text.strip() for text in texts)


def seed_repos(store: Store, project_id: str, paths: list[str]) -> None:
    for path in paths:
        store.add_repo(
            workspace_id=project_id,
            root_path=path,
            name=path.rsplit("/", 1)[-1],
            git_common_dir=f"{path}/.git",
            vcs_remote=None,
        )


def open_autonomy(page: Page) -> None:
    page.locator('.nav-item[data-page="settings"]').click()
    page.locator("#settings-nav .set-item", has_text="Autonomy").click()
    page.wait_for_function(
        "() => document.querySelectorAll('#settings-panel button.opt').length === 2"
    )


def pressed(page: Page, label: str) -> str | None:
    option = page.locator("#settings-panel button.opt", has_text=label)
    value = option.get_attribute("aria-pressed")
    return value if isinstance(value, str) else None


def focused_project(page: Page) -> str | None:
    value = page.evaluate(
        "() => document.activeElement ? document.activeElement.dataset.projectId || null : null"
    )
    return value if isinstance(value, str) else None


# ----- BC-12 R2 ---------------------------------------------------------------


def test_the_last_autonomy_click_wins(shipped: Shipped, client: Client) -> None:
    """R2: the older click's request lands last and must not win.

    The first click's POST is parked; the second click is made while it is
    parked; the parked one is then released. The user's last click was `ask`
    (2), so 2 is what the daemon must hold and what the page must show — and
    no more than two audited writes are made to get there (R2's
    `two_audit_rows` clause: a third write would be a record of nothing).
    """
    page = shipped.page
    assert client.request("/api/autonomy").json()["data"] == {"level": 2}
    open_autonomy(page)
    posts: list[object] = []
    page.on(
        "request",
        lambda request: posts.append(json.loads(request.post_data or "null"))
        if request.method == "POST" and request.url.endswith("/api/autonomy")
        else None,
    )
    install_shim(page, r"/api/autonomy$", hold=1)

    page.locator("#settings-panel button.opt", has_text=AUTO).click()
    page.wait_for_function("() => window.__shim.held.length === 1")
    page.locator("#settings-panel button.opt", has_text=ASK).click()
    assert page.evaluate("() => window.__releaseHeld()") == 1
    page.wait_for_function("() => window.__shim.consumed >= 2")

    level = client.request("/api/autonomy").json()["data"]
    assert level == {"level": 2}, f"the older click won: the daemon holds {level}"
    assert (pressed(page, ASK), pressed(page, AUTO)) == ("true", "false")
    assert posts == [{"level": 3}, {"level": 2}], posts
    assert shipped.page_errors == []


# ----- BC-12 R4 ---------------------------------------------------------------


def test_a_slow_path_read_does_not_paint_another_project(shipped: Shipped, store: Store) -> None:
    """R4: A's parked repos read lands after B's dialog painted B's paths."""
    page = shipped.page
    a = store.create_project(name="project A", description=None)
    b = store.create_project(name="project B", description=None)
    seed_repos(store, a.id, ["/code/ra-1", "/code/ra-2"])
    seed_repos(store, b.id, ["/code/rb-1", "/code/rb-2"])
    page.reload()
    page.wait_for_function("() => document.getElementById('stream-status').textContent === 'live'")
    open_projects(page)
    open_row(page, a.id, "project A")
    install_shim(page, rf"/api/projects/{a.id}/repos$", hold=1)

    page.locator("#proj-edit").click()
    page.wait_for_function("() => window.__shim.held.length === 1")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('dlg-project').open === false")
    open_row(page, b.id, "project B")
    open_edit(page)
    page.wait_for_function(
        "() => [...document.querySelectorAll('#p-paths .path-text')]"
        ".map((n) => n.textContent).join() === '/code/rb-1,/code/rb-2'"
    )

    assert page.evaluate("() => window.__releaseHeld()") == 1
    page.wait_for_function("() => window.__shim.consumed >= 1")

    assert dialog_paths(page) == ["/code/rb-1", "/code/rb-2"]
    assert page.input_value("#p-name") == "project B"
    assert shipped.page_errors == []


# ----- BC-12 R5 ---------------------------------------------------------------


def test_a_rebuild_does_not_swallow_an_edit_click(
    shipped: Shipped, store: Store, client: Client
) -> None:
    """R5 (DUP-2): a re-read between mouse-down and mouse-up keeps Edit in place.

    A second client creates a project; its event makes the page re-read the
    list and the open detail. The list read is parked until the mouse is down
    on `#proj-edit`, then released, and both replies are handled before the
    mouse comes up. Nothing about project P changed, so the button pressed is
    the button released on, and the click opens P's edit dialog.
    """
    page = shipped.page
    p = store.create_project(name="project P", description="pee")
    page.reload()
    page.wait_for_function("() => document.getElementById('stream-status').textContent === 'live'")
    open_projects(page)
    open_row(page, p.id, "project P")
    install_shim(page, r"/api/projects(/[0-9A-Za-z]+)?$", hold=1)

    created = client.post("/api/projects", {"name": "other client"})
    assert created.status == 200, created.body
    page.wait_for_function("() => window.__shim.held.length === 1")

    edit = page.locator("#proj-edit")
    box = edit.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    assert page.evaluate("() => window.__releaseHeld()") == 1
    # The list reply and the detail reply it causes, both handled.
    page.wait_for_function("() => window.__shim.consumed >= 2")
    assert page.locator("#proj-list .proj-row", has_text="other client").count() == 1
    page.mouse.up()

    assert eventually(page, "() => document.getElementById('dlg-project').open === true"), (
        "the click on Edit was swallowed by the rebuild"
    )
    assert page.locator("#dlg-project-title").inner_text() == "Edit project"
    assert page.input_value("#p-name") == "project P"
    assert shipped.page_errors == []
    assert shipped.errors == []


# ----- BC-18 (Projects) -------------------------------------------------------


def test_row_focus_survives_an_event(shipped: Shipped, store: Store, client: Client) -> None:
    """U41's `ui.row_focus_survives`: a rebuild keeps the keyboard user's place.

    Twice: an event that adds a row (the focused row is unchanged and must be
    the same node), then an event that renames the focused project (its row is
    redrawn and focus must follow its key). The DOM signal is the row the event
    produced — the rebuild has landed when it is on screen.
    """
    page = shipped.page
    alpha = store.create_project(name="alpha", description=None)
    store.create_project(name="beta", description=None)
    page.reload()
    page.wait_for_function("() => document.getElementById('stream-status').textContent === 'live'")
    open_projects(page)
    page.locator(f'#proj-list .proj-row[data-project-id="{alpha.id}"]').focus()
    assert focused_project(page) == alpha.id  # the control

    added = client.post("/api/projects", {"name": "gamma"})
    assert added.status == 200, added.body
    page.wait_for_selector('#proj-list .proj-row:has(.proj-name:text-is("gamma"))')
    assert focused_project(page) == alpha.id, "the added row's rebuild dropped focus"

    renamed = client.post(f"/api/projects/{alpha.id}/rename", {"name": "alpha renamed"})
    assert renamed.status == 200, renamed.body
    page.wait_for_selector('#proj-list .proj-row:has(.proj-name:text-is("alpha renamed"))')
    assert focused_project(page) == alpha.id, "the renamed row's rebuild dropped focus"
    assert shipped.page_errors == []
    assert shipped.errors == []


# ----- BC-24 ------------------------------------------------------------------


def test_a_refused_remove_is_shown(shipped: Shipped, store: Store) -> None:
    """U18: a refused path removal says so, as a refused add already does."""
    page = shipped.page
    project = store.create_project(name="paths", description=None)
    seed_repos(store, project.id, ["/code/one", "/code/two"])
    page.reload()
    page.wait_for_function("() => document.getElementById('stream-status').textContent === 'live'")
    open_projects(page)
    open_row(page, project.id, "paths")
    open_edit(page)
    page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 2")
    page.route(
        f"**/api/projects/{project.id}/repos/remove",
        lambda route: route.fulfill(
            status=400, content_type="application/json", body=refused("p13-refused")
        ),
    )

    page.locator("#p-paths button[data-repo-id]").first.click()

    shown = eventually(
        page,
        "() => { const n = document.getElementById('p-refusal');"
        " return !n.hidden && n.textContent.includes('p13-refused'); }",
    )
    assert shown, f"the refusal is silent: #p-refusal={page.locator('#p-refusal').text_content()!r}"
    assert dialog_paths(page) == ["/code/one", "/code/two"]
    assert shipped.page_errors == []


def test_a_refused_level_change_is_shown(shipped: Shipped, client: Client) -> None:
    """U24: a refused autonomy change shows the error and its correlation id;
    an unreachable one keeps saying it did not reach the server (control)."""
    page = shipped.page
    open_autonomy(page)

    def refuse(route: Route) -> None:
        if route.request.method == "POST":
            route.fulfill(
                status=400, content_type="application/json", body=refused("p13-corr")
            )
        else:
            route.continue_()

    page.route("**/api/autonomy", refuse)
    page.locator("#settings-panel button.opt", has_text=AUTO).click()
    shown = eventually(
        page, "() => document.getElementById('settings-note').textContent.includes('p13-corr')"
    )
    assert shown, (
        "the refusal is silent: "
        f"#settings-note={page.locator('#settings-note').text_content()!r}"
    )
    assert pressed(page, AUTO) == "false"
    page.unroute("**/api/autonomy", refuse)

    def abort(route: Route) -> None:
        if route.request.method == "POST":
            route.abort()
        else:
            route.continue_()

    page.route("**/api/autonomy", abort)
    page.locator("#settings-panel button.opt", has_text=AUTO).click()
    assert eventually(
        page,
        "(want) => document.getElementById('settings-note').textContent === want",
        SETTINGS_UNREACHABLE,
    ), page.locator("#settings-note").text_content()
    page.unroute("**/api/autonomy", abort)
    assert client.request("/api/autonomy").json()["data"] == {"level": 2}
    assert pressed(page, AUTO) == "false"
    assert shipped.page_errors == []


def test_a_retried_save_does_not_resend_the_rename(
    shipped: Shipped, store: Store, client: Client
) -> None:
    """U17: the rename landed, the description was refused; the retry sends
    only the description — a rename is an audited write, and a second one is
    a record of something that did not happen."""
    page = shipped.page
    project = store.create_project(name="alpha", description="old")
    page.reload()
    page.wait_for_function("() => document.getElementById('stream-status').textContent === 'live'")
    posts: list[str] = []
    page.on(
        "request",
        lambda request: posts.append(request.url.rsplit("/", 1)[-1])
        if request.method == "POST" and f"/api/projects/{project.id}/" in request.url
        else None,
    )
    open_projects(page)
    open_row(page, project.id, "alpha")
    open_edit(page)
    page.fill("#p-name", "alpha2")
    page.fill("#p-desc", "new")
    describe = f"**/api/projects/{project.id}/description"

    def refuse(route: Route) -> None:
        route.fulfill(
            status=400, content_type="application/json", body=refused("p13-save")
        )

    page.route(describe, refuse)
    page.locator("#p-save").click()
    assert eventually(
        page,
        "() => { const n = document.getElementById('p-refusal');"
        " return !n.hidden && n.textContent.includes('p13-save'); }",
    )
    page.unroute(describe, refuse)
    page.locator("#p-save").click()
    assert eventually(page, "() => document.getElementById('dlg-project').open === false")

    assert posts == ["rename", "description", "description"], posts
    detail = client.request(f"/api/projects/{project.id}").json()["data"]
    assert isinstance(detail, dict)
    stored = detail["project"]
    assert isinstance(stored, dict)
    assert (stored["name"], stored["description"]) == ("alpha2", "new")
    assert shipped.page_errors == []
