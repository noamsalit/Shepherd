"""T9.1 — the Projects page, driven in a real browser against the real routes.

**This file is the acceptance test for D57's seven verbs.** Phases 1, 3 and 4
built a migration, eleven store verbs, seven tools and seven routes, and until
this file ran nothing had driven any of them from a consumer. Every assertion
below goes through chromium -> a real socket -> `web/routes.py` -> `invoke()` ->
a real `Store`, because a page proved against a stubbed `fetch` proves the
page's opinion of the API and not the API.

**The seam is the served origin, not the file.** `projects.js` is imported as
`/static/projects.js` from the same `ThreadingHTTPServer` the rest of
`tests/web/` uses, so the module graph resolves the way it resolves in
production and the `Origin` header on every mutation is the real one §13 checks.

**The shell around it is `tests/web/fixtures/shell_harness.html`**, read from
disk and served at a path the server does not know, with two edits made in
memory and named here: the stylesheet `<link>` is repointed at `/static/app.css`
(the fixture's relative href does not resolve at an http origin) and a module
`<script>` is appended that imports `mountProjects` and calls it. The fixture
itself is never written to — T5.2 owns it, and its `#page-projects` root is the
class contract this page fills.

**What this file does not prove.** It does not prove `index.html` mounts the
page (T5.3 and the integration pass own that), it does not prove that a click on
a session anchor opens the Flock (the anchor's shape is asserted; the routing is
the shell's), and it proves no pixel — `tools/render_check.py` is Phase 10's. It
also cannot prove the sentence D61 asks for before the delete button: see
`docs/plans/projects-ui-blockers/t9-1.md`.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

from web.conftest import NOW, Client, Response  # noqa: E402

from shepherd.core.states import Origin, Ownership  # noqa: E402
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict  # noqa: E402
from shepherd.store.db import Store  # noqa: E402
from shepherd.store.models import UNASSIGNED_PROJECT_ID  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HARNESS = FIXTURES / "shell_harness.html"

#: The path the harness is served at. It is deliberately one the server answers
#: 404 for: playwright fulfils it from memory, so the shell markup is the
#: fixture's and everything *else* — the module, the stylesheet, the seven API
#: calls — is the server's.
HARNESS_PATH = "/__shell_harness__"

MOUNT = (
    '<script type="module">\n'
    "import { mountProjects } from '/static/projects.js';\n"
    "window.__projects = mountProjects();\n"
    "</script>\n"
)


def harness_html() -> str:
    """The committed fixture, with the two edits this origin requires."""
    raw = HARNESS.read_text(encoding="utf-8")
    repointed = raw.replace(
        'href="../../../src/shepherd/web/static/app.css"', 'href="/static/app.css"'
    )
    assert repointed != raw, "the harness stylesheet link moved"
    return repointed.replace("</body>", MOUNT + "</body>")


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    """One chromium for the module: a launch per test is a second of nothing."""
    with sync_playwright() as driver:
        launched = driver.chromium.launch()
        try:
            yield launched
        finally:
            launched.close()


class Console:
    """Every console error and page exception, so a green assertion on a broken
    page is not possible — `render_check.py`'s rule, applied per test."""

    def __init__(self) -> None:
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


@pytest.fixture()
def console() -> Console:
    return Console()


@pytest.fixture()
def projects_page(
    browser: Browser, client: Client, console: Console, server: ThreadingHTTPServer
) -> Iterator[Page]:
    """The harness, open on the Projects page, mounted, first paint done."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    # Five seconds against a loopback server is a decision that never arrived;
    # the default 30 makes a red test cost half a minute to read.
    page.set_default_timeout(5000)
    console.watch(page)
    body = harness_html()
    page.route(
        f"{client.origin}{HARNESS_PATH}",
        lambda route: route.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=body
        ),
    )
    page.goto(f"{client.origin}{HARNESS_PATH}")
    page.click('.nav-item[data-page="projects"]')
    try:
        yield page
    finally:
        context.close()


# ----- store helpers ----------------------------------------------------------


def git_env() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
        GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="shepherd-test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="shepherd-test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
    )
    return environment


def make_repo(root: Path) -> Path:
    """A throwaway working tree with a real `.git` — `add_repo` probes git for
    D48's binding key, so a directory that is not a repo is refused by design."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=root,
        env=git_env(),
        capture_output=True,
        check=True,
    )
    return root


def running_session(store: Store, project_id: str, engine_session_id: str) -> str:
    """Alive by the only definition `store/` uses: `ended_at IS NULL`."""
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=project_id,
        repo_id=None,
        cwd="/tmp",
        started_at=NOW,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    ).id


def ended_session(store: Store, project_id: str, engine_session_id: str) -> str:
    session_id = running_session(store, project_id, engine_session_id)
    store.apply_stop_verdict(
        session_id=session_id,
        verdict=Verdict(
            stop_reason=StopReason.COMPLETED,
            bucket=Bucket.FINISHED,
            why="done",
            confidence=1.0,
            decided_by=DecidedBy.HEURISTIC,
            next_actions=(),
            waiting_on=None,
            missing=(),
        ),
        ended_at="2026-09-22T11:00:00.000Z",
        exit_code=0,
    )
    return session_id


def answer_of(response: Response) -> dict[str, object]:
    """The `data` half of `{ok, data, error, correlation_id}`, as a mapping."""
    body = response.json()
    data = body["data"]
    assert isinstance(data, dict), body
    return data


def open_project(page: Page, name: str) -> None:
    """Click the named row and wait for the detail pane to carry its title."""
    page.click(f'#page-projects .proj-row:has(.proj-name:text-is("{name}"))')
    page.wait_for_selector(f'#page-projects .proj-title:text-is("{name}")', timeout=5000)


# ----- the list ---------------------------------------------------------------


def test_the_list_renders_every_project_with_unassigned_pinned_last(
    projects_page: Page, store: Store, console: Console
) -> None:
    """U14's first half, and D59's pin, over `list_projects`.

    The two declared projects are created **out of alphabetical order**, so
    "last" is a pin rather than a coincidence of a sort nobody wrote.
    """
    store.create_project(name="zebra", description=None)
    store.create_project(name="alpha", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')

    rows = projects_page.locator("#page-projects .proj-row")
    rows.first.wait_for(timeout=5000)
    names = rows.locator(".proj-name").all_inner_texts()

    assert names[-1] == "Unassigned", names
    assert sorted(names[:-1]) == ["alpha", "zebra"], names
    assert console.messages == []


def test_unassigned_offers_no_lifecycle_control_at_all(
    projects_page: Page, store: Store, console: Console
) -> None:
    """E7/E8/E9 at the consumer: absent, not disabled.

    A disabled button still says "this is a thing you may one day do here", and
    for the reserved project it is not — the store refuses all three verbs. The
    assertion is over the *whole* detail pane rather than over three named ids,
    so a fourth control added later is caught by the same line.
    """
    store.create_project(name="payments", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")
    assert projects_page.locator("#proj-detail .proj-acts button").count() == 2

    open_project(projects_page, "Unassigned")

    assert projects_page.locator("#proj-detail .proj-acts").count() == 0
    assert projects_page.locator("#proj-detail button").count() == 1, "only Back"
    assert projects_page.locator('#proj-detail button[aria-label="Back"]').count() == 1
    assert console.messages == []


def test_the_detail_shows_repo_paths_in_full_and_sessions_as_flock_links(
    projects_page: Page, store: Store, client: Client, tmp_path: Path, console: Console
) -> None:
    """U14: the paths **are** §13's allowlist, so they are shown whole — never
    a basename, never an ellipsis — and a session on a project is a link into
    the Flock rather than a dead line of text.

    The path is registered through the real `add_repo` route so the string on
    the page is the one the store canonicalized, not the one a test typed.
    """
    project = store.create_project(name="payments", description="the api")
    repo = make_repo(tmp_path / "code" / "payments-api")
    added = client.post(f"/api/projects/{project.id}/repos/add", {"root_path": str(repo)})
    assert answer_of(added)["added"] is True, added.body
    session_id = running_session(store, project.id, "eng-flock")

    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")

    path_text = projects_page.locator("#proj-detail .path-text").inner_text()
    assert path_text == str(repo), path_text
    assert projects_page.locator("#proj-detail .desc").first.inner_text() == "the api"

    link = projects_page.locator(f'#proj-detail a.mini-open[data-session-id="{session_id}"]')
    assert link.count() == 1
    assert link.get_attribute("data-page") == "flock"
    assert link.get_attribute("href") == f"#flock/session/{session_id}"
    assert console.messages == []


def test_the_work_source_block_says_not_built_rather_than_offering_a_form(
    projects_page: Page, store: Store, console: Console
) -> None:
    """D63/D64/W3: M5's `queue` table does not exist, so there is nothing
    behind a provider picker. RD6's rule — a capability that lands later
    renders labelled and inert — and the label is the whole control."""
    store.create_project(name="payments", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")

    block = projects_page.locator("#proj-detail .section:has(.field-label:text-is('Work source'))")
    assert block.count() == 1
    # `text_content`, not `inner_text`: `.soon` is `text-transform: uppercase`
    # in the stylesheet, so the rendered string is the design's and the DOM
    # string is this module's. The page writes the words; the CSS shouts them.
    assert block.locator(".soon").text_content() == "not built"
    assert block.locator("select, input, button").count() == 0
    assert console.messages == []


# ----- create, rename, and the two repo verbs --------------------------------


def test_the_new_project_dialog_creates_a_project(
    projects_page: Page, store: Store, console: Console
) -> None:
    """`create_project` through the page — E1's half that a consumer can see:
    the project is keyed by id, so a second project of the same name is a
    second row rather than an overwrite."""
    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "payments")
    projects_page.fill("#p-desc", "the api")
    projects_page.click("#p-save")

    projects_page.wait_for_selector('.proj-name:text-is("payments")', timeout=5000)
    made = [row for row in store.list_workspaces() if row.name == "payments"]
    assert len(made) == 1, store.list_workspaces()
    assert made[0].description == "the api"
    assert console.messages == []


def test_the_edit_dialog_renames_the_project(
    projects_page: Page, store: Store, console: Console
) -> None:
    """`rename_project`: identity is the id, a name is a label (D57)."""
    project = store.create_project(name="payments", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")

    projects_page.click("#proj-edit")
    projects_page.fill("#p-name", "billing")
    projects_page.click("#p-save")

    projects_page.wait_for_selector('.proj-name:text-is("billing")', timeout=5000)
    renamed = store.get_workspace(project.id)
    assert renamed is not None
    assert renamed.name == "billing"
    assert console.messages == []


def test_a_path_is_added_and_removed_from_the_edit_dialog(
    projects_page: Page, store: Store, tmp_path: Path, console: Console
) -> None:
    """`add_repo` and `remove_repo`, and the warning that must be beside them.

    U14 puts path editing in the dialog rather than inline, because adding one
    widens §13's allowlist and that sentence has to be on screen when it
    happens (D22/D58). The removal is asserted on the store's own list: the
    `repo` row is kept and only the edge goes (E6), so "removed" is a fact
    about `list_repos`, not about the page's own array.
    """
    project = store.create_project(name="payments", description=None)
    repo = make_repo(tmp_path / "code" / "payments-api")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")
    projects_page.click("#proj-edit")

    warning = projects_page.locator("#dlg-project .dlg-warn").inner_text()
    assert "widens where Shepherd may start sessions" in warning

    projects_page.fill("#p-new-path", str(repo))
    projects_page.click("#p-add-path")
    projects_page.wait_for_selector(f'#p-paths .path-text:text-is("{repo}")', timeout=5000)
    assert [row.root_path for row in store.list_repos(project.id)] == [str(repo)]

    projects_page.click("#p-paths .path button")
    projects_page.wait_for_selector("#p-paths .path", state="detached", timeout=5000)
    assert store.list_repos(project.id) == []
    assert console.messages == []


def test_a_path_that_is_not_a_repository_is_refused_in_words(
    projects_page: Page, store: Store, tmp_path: Path, console: Console
) -> None:
    """The refusal `add_repo` answers with is a sentence, and the page shows it.

    A path that does not probe as a git repo has no `git_common_dir`, so a
    session started under it later would bind to `Unassigned` — the silent
    failure this page exists to make loud.
    """
    store.create_project(name="payments", description=None)
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")
    projects_page.click("#proj-edit")

    projects_page.fill("#p-new-path", str(plain))
    projects_page.click("#p-add-path")

    refusal = projects_page.locator("#p-refusal")
    refusal.wait_for(timeout=5000)
    assert "not a git repository" in refusal.inner_text()
    assert console.messages == []


# ----- the reserved project, through HTTP -------------------------------------
#
# E7/E8/E9 are proved against `store/` in `tests/store/test_verbs.py` and
# against the tools in `tests/toolsurface/`. What is left to prove here is that
# the *route* carries the refusal to a consumer as a value — a `StoreError` that
# escaped would reach the page as `request failed`, which is not a reason
# anything can draw, and the page above renders no control for these three at
# all. Both halves are needed: the absent control is the design, and the
# refusal is what makes the design safe rather than load-bearing.


def test_unassigned_refuses_rename_through_http(client: Client) -> None:
    """E8 over the wire."""
    answer = client.post(f"/api/projects/{UNASSIGNED_PROJECT_ID}/rename", {"name": "mine"})

    assert answer.status == 200, answer.body
    data = answer_of(answer)
    assert data["renamed"] is False
    assert "Unassigned" in str(data["refused"])


def test_unassigned_refuses_delete_through_http(client: Client) -> None:
    """E9 over the wire, with no `on_running` in the body at all."""
    answer = client.post(f"/api/projects/{UNASSIGNED_PROJECT_ID}/delete", {})

    assert answer.status == 200, answer.body
    data = answer_of(answer)
    assert data["deleted"] is False
    assert "Unassigned" in str(data["refused"])


def test_unassigned_refuses_add_repo_through_http(client: Client, tmp_path: Path) -> None:
    """E7 over the wire: the reserved project's allowlist is never widened by
    hand — it is what every *discovered* session's spawn is validated against."""
    repo = make_repo(tmp_path / "work" / "api")

    answer = client.post(
        f"/api/projects/{UNASSIGNED_PROJECT_ID}/repos/add", {"root_path": str(repo)}
    )

    assert answer.status == 200, answer.body
    data = answer_of(answer)
    assert data["added"] is False
    assert "Unassigned" in str(data["refused"])


# ----- D61's delete, all four branches ---------------------------------------


def open_delete(page: Page, name: str) -> None:
    open_project(page, name)
    page.click("#proj-delete")
    page.wait_for_selector("#dlg-delete[open]", timeout=5000)


def test_the_delete_dialog_says_what_will_be_destroyed_before_the_button(
    projects_page: Page, store: Store, console: Console
) -> None:
    """D61's first sentence, and the one the record does not carry.

    A person told `orphaned=('s-live',)` is not told that the finished sessions
    went with the project. `DeletePlan.doomed` is that list and the tool
    discards it, so the page derives it from the detail it already holds —
    every session in the project whose `ended_at` is set. That derivation is
    the store's own (`running` is `ended_at IS NULL`) and it is a **copy**: see
    `docs/plans/projects-ui-blockers/t9-1.md`.

    The count is asserted **before** any POST, and the project is still there
    when it is: the sentence is what the button is for, not what it produced.
    """
    project = store.create_project(name="payments", description=None)
    ended_session(store, project.id, "eng-1")
    ended_session(store, project.id, "eng-2")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")

    body = projects_page.locator("#dlg-delete-body").inner_text()
    assert "2 session records" in body, body
    assert store.get_workspace(project.id) is not None, "nothing may be written yet"

    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector("#dlg-delete-outcome", timeout=5000)

    assert store.get_workspace(project.id) is None
    outcome = projects_page.locator("#dlg-delete-outcome").inner_text()
    assert "2 session records destroyed" in outcome, outcome
    assert console.messages == []


def test_cancel_writes_nothing(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The exit criterion, proved on the wire rather than on the outcome.

    Asserting the project survives would also pass if the page had POSTed and
    the store had refused. Every request the page made is recorded, and the
    claim is that the delete route was never called at all.
    """
    project = store.create_project(name="payments", description=None)
    running_session(store, project.id, "eng-live")
    posted: list[str] = []
    projects_page.on(
        "request",
        lambda request: posted.append(request.url) if request.method == "POST" else None,
    )
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")

    projects_page.click("#dlg-delete-cancel")

    projects_page.wait_for_selector("#dlg-delete[open]", state="detached", timeout=5000)
    assert posted == [], posted
    assert store.get_workspace(project.id) is not None
    assert console.messages == []


def test_the_delete_dialog_renders_the_three_choices_from_the_refusal(
    projects_page: Page, store: Store, console: Console
) -> None:
    """E13, and the shape of the whole dialog: **default-refuse**.

    The first POST carries no `on_running` at all — the value cannot be edited
    out of the request because it was never in it — and the three choices are
    drawn out of the refusal the server answered with, including the running
    session ids it named. A page that rendered them from its own idea of what
    is running would show a choice list for a session that had already ended.
    """
    project = store.create_project(name="payments", description=None)
    live = running_session(store, project.id, "eng-live")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")

    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="orphan"]', timeout=5000)

    body = projects_page.locator("#dlg-delete-body").inner_text()
    assert "still running in this project" in body, body
    assert live in projects_page.locator("#dlg-delete-live").inner_text()
    choices = projects_page.locator(".dlg-choice").evaluate_all(
        "nodes => nodes.map(node => node.dataset.choice)"
    )
    assert choices == ["kill_sessions", "orphan", "cancel"], choices
    assert store.get_workspace(project.id) is not None
    assert console.messages == []


def test_orphan_moves_the_running_sessions_and_names_every_consequence(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The second choice, and the three fields a person is owed after it.

    `orphaned` is where the live work went, `destroyed` is what the cascade
    took, and `severed` is the lineage links nulled on the sessions that
    survived. The retried session is the one that makes `severed` non-empty:
    without it the field would render empty in every test and nothing would
    say whether the page can show it.
    """
    project = store.create_project(name="payments", description=None)
    gone = ended_session(store, project.id, "eng-done")
    live = running_session(store, project.id, "eng-live")
    store.link_retry(session_id=live, retry_of=gone)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="orphan"]', timeout=5000)

    projects_page.click('.dlg-choice[data-choice="orphan"]')

    projects_page.wait_for_selector("#dlg-delete-outcome", timeout=5000)
    outcome = projects_page.locator("#dlg-delete-outcome").inner_text()
    assert store.get_workspace(project.id) is None
    moved = store.get_session(live)
    assert moved is not None
    assert moved.workspace_id == UNASSIGNED_PROJECT_ID
    assert live in outcome, outcome
    assert "1 session record destroyed" in outcome, outcome
    assert "retry_of" in outcome, outcome
    assert console.messages == []


def test_a_kill_that_does_not_land_keeps_the_project_and_says_so(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The third choice's honest failure, which is the shipped default.

    `web/conftest.py` registers `refuses_every_kill` — the same safe injection
    `build_project_tools` carries — so the commit half re-derives a still-running
    project and refuses. That is not a bug in the page and the page must not
    round it up to a delete: the project is still there afterwards and the
    dialog says which sessions are still running.

    **The session is `owned_session` rather than `running_session` since the QA
    remediation pass.** Defect 4 made "Stop them, then delete" a choice the page
    only offers when the server's `killable` split says the stop can reach
    something, and `killable` is `runner_handle IS NOT NULL`. Every session in
    this file used to be attached, so the choice was offered over a plan that
    already said it could not work — and this test clicked it. It is the
    *injected* kill that refuses here, which is a different thing from having no
    pane, and the handle is what separates the two.
    """
    project = store.create_project(name="payments", description=None)
    live = owned_session(store, project.id, "eng-live")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="kill_sessions"]', timeout=5000)

    projects_page.click('.dlg-choice[data-choice="kill_sessions"]')

    projects_page.wait_for_selector("#dlg-delete-body:has-text('were not stopped')", timeout=5000)
    assert store.get_workspace(project.id) is not None
    assert live in projects_page.locator("#dlg-delete-live").inner_text()
    assert console.messages == []


@pytest.fixture()
def kills_the_owned_one(store: Store, projects_root: Path) -> list[str]:
    """Re-register the project verbs behind a kill that **lands for one
    session and not the other** — the mixed project.

    `web/conftest.py` injects `refuses_every_kill`, which is the shipped safe
    default and cannot produce this case. The distinction it stands for is
    real: the kill path answers `no_pane(...)` for any session with no runner
    handle, which is every *attached* one, so a project holding one owned and
    one discovered session gets a delete that stops the first and is then
    refused over the second. `DeletePlan.running` does not carry that
    distinction, so the page cannot warn about it in advance — it can only show
    what came back, which is what this exercises.

    The kill lands the way production lands one: through `apply_stop_verdict`,
    whose statement writes `ended_at`, because a kill that returns `True` and
    touches no row is a claim the commit half is built to refuse.
    """
    from shepherd.toolsurface.registry import reset_registry
    from shepherd.toolsurface.tools_m1 import register_read_tools
    from shepherd.toolsurface.tools_projects import register_project_tools

    from chokepoint_fixture import install_test_chokepoint

    asked: list[str] = []
    killable: list[str] = []

    def kill(session_id: str) -> bool:
        asked.append(session_id)
        if session_id not in killable:
            return False
        store.apply_stop_verdict(
            session_id=session_id,
            verdict=Verdict(
                stop_reason=StopReason.USER_EXITED,
                bucket=Bucket.FINISHED,
                why="the delete stopped it",
                confidence=1.0,
                decided_by=DecidedBy.MECHANICAL,
                next_actions=(),
                waiting_on=None,
                missing=(),
            ),
            ended_at="2026-09-22T12:00:00.000Z",
            exit_code=None,
        )
        return True

    reset_registry()
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_project_tools(
        store=store, kill=kill, publish=lambda event: None, now=lambda: NOW
    )
    return killable


def test_a_partly_landed_kill_shows_what_it_stopped_on_the_refusal(
    projects_page: Page, store: Store, kills_the_owned_one: list[str], console: Console
) -> None:
    """`killed` is populated on a **refusal**, and the page must show it there.

    Two sessions, one killable. The commit half re-derives the running set, sees
    one still alive and refuses the delete — correctly, because deleting the row
    of a session that is still running is the one thing this verb must never do.
    But one session really was stopped, and a dialog that showed `killed` only
    on success would tell a person "nothing happened" about a stopped agent.

    `owned` now carries a `runner_handle`, so the name is true of the row and
    not only of the fixture's dict: the server's `killable` split reads that
    column, and the QA remediation pass made the page render the choice out of
    it (defect 4).
    """
    project = store.create_project(name="payments", description=None)
    owned = owned_session(store, project.id, "eng-owned")
    attached = running_session(store, project.id, "eng-attached")
    kills_the_owned_one.append(owned)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="kill_sessions"]', timeout=5000)

    projects_page.click('.dlg-choice[data-choice="kill_sessions"]')

    projects_page.wait_for_selector("#dlg-delete-body:has-text('were not stopped')", timeout=5000)
    live = projects_page.locator("#dlg-delete-live").inner_text()
    assert "Already stopped by this attempt:" in live, live
    assert owned in live and attached in live, live
    assert store.get_workspace(project.id) is not None
    stopped = store.get_session(owned)
    assert stopped is not None and stopped.ended_at is not None
    assert console.messages == []


def test_the_page_renders_the_correlation_id_when_a_call_fails(
    projects_page: Page, store: Store, console: Console
) -> None:
    """E14, split honestly across two proofs.

    That a raising handler becomes `{"ok": false, "error": "request failed",
    "correlation_id": …}` is `registry.py:69` and `:318-319`, proved in
    `tests/toolsurface/`. What **this** file can prove is the other half: that
    the page shows the id rather than swallowing it, because an id a person can
    quote is the whole of what §13 leaves behind. The envelope is therefore
    injected at the transport, built from the shipped literal rather than from
    a string typed here — rename `GENERIC_ERROR` and this goes red.
    """
    from shepherd.toolsurface.registry import GENERIC_ERROR

    store.create_project(name="payments", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")
    projects_page.route(
        "**/api/projects/*/rename",
        lambda route: route.fulfill(
            # 400 with `ok: false` is what `server.py::_fail` sends when
            # `invoke()` fails — the status is part of the shape being rendered.
            status=400,
            content_type="application/json",
            body=(
                '{"ok": false, "data": null, "error": "'
                + GENERIC_ERROR
                + '", "correlation_id": "cid-01JPROJ"}'
            ),
        ),
    )

    projects_page.click("#proj-edit")
    projects_page.fill("#p-name", "billing")
    projects_page.click("#p-save")

    refusal = projects_page.locator("#p-refusal")
    refusal.wait_for(timeout=5000)
    assert refusal.inner_text() == f"{GENERIC_ERROR} (cid-01JPROJ)"
    # chromium logs every non-2xx as a console error, so this is the one test
    # in the file whose console is not empty — and it is that, and nothing else.
    assert all("400" in message for message in console.messages), console.messages


# ============================================================================
# The QA remediation pass (workflow wf-20260921T212808Z-9172ed6b).
#
# Every test below was written against a defect a QA agent found by driving a
# *seeded* product — several projects, sessions in all eight buckets, long
# paths, long titles, duplicate names — and none of which any committed test
# could see, because everything above this line seeds one project and at most
# two sessions. The seeding helpers come first, then one test per defect, each
# naming the defect it closes.
#
# `docs/plans/projects-ui-blockers/qa-remfix.md` is the ledger.
# ============================================================================


def owned_session(store: Store, project_id: str, engine_session_id: str) -> str:
    """A running session Shepherd **owns** — `runner_handle IS NOT NULL`.

    This is the distinction `DeletePlan.killable` is: `reads.py:283` splits the
    running set on that column because the shipped kill path asks `handle_for`
    and answers `no_pane(...)` for the rest. Every running session in this file
    before this helper was *attached*, so `killable` was empty in every test and
    the page's "Stop them, then delete" choice was never exercised against a
    plan that said the stop could actually work.
    """
    from shepherd.core.runner import RunnerHandle

    session_id = running_session(store, project_id, engine_session_id)
    store.set_runner_handle(
        session_id,
        RunnerHandle(runner="tmux", socket="shepherd", session_name=f"shp_{engine_session_id}"),
    )
    return session_id


def seed_several_projects(store: Store) -> dict[str, str]:
    """Four projects, two of them sharing a name, and sessions on three.

    The shape is QA's harness seed, narrowed to what this page can show: a
    project with more session records than the page's old local filter counted,
    a project with nothing in it, and **two projects with the same name** —
    which `create_project` permits by design (E1, keyed by id, never by name)
    and which no committed test had ever put on screen together.
    """
    made: dict[str, str] = {}
    made["busy"] = store.create_project(name="payments", description="the api").id
    made["quiet"] = store.create_project(name="docs-site", description=None).id
    made["twin_a"] = store.create_project(name="twin", description="the first one").id
    made["twin_b"] = store.create_project(name="twin", description="the second one").id
    for n in range(3):
        ended_session(store, made["busy"], f"eng-done-{n}")
    made["live"] = running_session(store, made["busy"], "eng-live")
    return made


# ----- defect 1: the dialog undercounted what the delete destroys ------------


def test_the_delete_dialog_counts_every_session_record_the_delete_takes(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 1 (HIGH).** The dialog said "6 session records" over a delete
    that took 8.

    `commit_project_delete` runs `DELETE FROM session WHERE workspace_id = ?`:
    the running rows go too. The page filtered `ended_at !== null` and showed
    the complement, which is the count for the **orphan** branch presented as
    the unconditional one — so the sentence in front of the one destructive
    verb on this page understated it by exactly the number of live sessions.

    `DeletePlan.doomed` is the server's own answer to the same question and
    `reads.py:285-291` was written in anticipation of this drift. The page now
    renders the whole session list before the button (which is what `doomed` is
    for `refuse` and for `kill_sessions`) and `answer.doomed` after it.
    """
    project = store.create_project(name="payments", description=None)
    for n in range(3):
        ended_session(store, project.id, f"eng-done-{n}")
    live = running_session(store, project.id, "eng-live")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")

    body = projects_page.locator("#dlg-delete-body").inner_text()
    assert "4 session records" in body, body
    assert "3 session records" not in body, body

    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="orphan"]', timeout=5000)

    # The server's list, rendered as the server's list: four ids, the live one
    # among them, on the refusal where `doomed` first becomes readable.
    doomed = projects_page.locator("#dlg-delete-doomed").inner_text()
    assert live in doomed, doomed
    assert doomed.count("\n") >= 4, doomed
    assert console.messages == []


# ----- defect 2: an unreachable daemon was swallowed -------------------------


def test_a_create_that_never_reaches_the_server_says_so(
    projects_page: Page, console: Console
) -> None:
    """**Defect 2 (HIGH).** With `controld` stopped, Create did nothing at all:
    the dialog stayed open, `#p-refusal` stayed hidden and empty, and the only
    trace was an unhandled `Failed to fetch` on the console.

    `envelope()` runs on a *resolved* response, so a rejected `fetch` walked
    past every refusal path this page has. The element built for exactly this
    case (`projects.js:443-447`) was never reached. `session.js` already had
    the sentence; four of six modules had not caught the rejection at all.
    """
    projects_page.route("**/api/projects", lambda route: route.abort("failed"))

    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "payments")
    projects_page.click("#p-save")

    refusal = projects_page.locator("#p-refusal")
    refusal.wait_for(timeout=5000)
    assert "did not reach the server" in refusal.inner_text(), refusal.inner_text()
    assert projects_page.locator("#dlg-project[open]").count() == 1
    assert [m for m in console.messages if "pageerror" in m] == [], console.messages


# ----- defect 3: the page lied about a verb that exists ----------------------


def test_the_edit_dialog_changes_the_description(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 3 (MEDIUM).** `set_project_description` is built, routed and
    registered — QA drove it over HTTP — and the page disabled the field with
    "no verb changes it in this build".

    That sentence told a person the only way to fix a typo in a description was
    to delete the project, which is the one destructive verb on the page. Eight
    of D57's nine verbs had a caller here; this was the ninth.
    """
    project = store.create_project(name="payments", description="the api")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "payments")

    projects_page.click("#proj-edit")
    assert projects_page.locator("#p-desc").is_enabled()
    projects_page.fill("#p-desc", "the billing api, renamed")
    projects_page.click("#p-save")

    projects_page.wait_for_selector(
        "#proj-detail .desc:text-is('the billing api, renamed')", timeout=5000
    )
    described = store.get_workspace(project.id)
    assert described is not None
    assert described.description == "the billing api, renamed"
    assert console.messages == []


# ----- defect 4: the killable split was computed, shipped and thrown away ----


def test_the_stop_choice_is_refused_in_advance_when_nothing_is_killable(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 4 (MEDIUM).** On the refusal the server sends `killable: []`
    and `unkillable: [ids]` — it already knows the stop cannot work. The page
    offered "Stop them, then delete" as the primary danger choice anyway, and
    the click was refused a second time.

    `tools_projects_delete.py:122` states the intent: *the split of `running`
    is what lets it gray a choice that cannot work rather than discovering that
    by click.* Every running session here is attached, so `runner_handle` is
    NULL on both and `killable` is empty.
    """
    project = store.create_project(name="payments", description=None)
    running_session(store, project.id, "eng-attached-a")
    running_session(store, project.id, "eng-attached-b")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="orphan"]', timeout=5000)

    stop = projects_page.locator('.dlg-choice[data-choice="kill_sessions"]')
    assert stop.is_disabled(), stop.inner_text()
    assert "Shepherd does not own" in stop.inner_text(), stop.inner_text()
    assert projects_page.locator('.dlg-choice[data-choice="orphan"]').is_enabled()
    assert console.messages == []


def test_the_stop_choice_is_offered_when_the_server_says_one_is_killable(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The other branch of the same gate, named because a control that only
    exercised the disabled side would certify half of it.

    One owned session (`runner_handle` set) and one attached: `killable` is
    non-empty, so the choice is live — and the note says which sessions it
    cannot reach rather than letting the click discover them.
    """
    project = store.create_project(name="payments", description=None)
    owned_session(store, project.id, "eng-owned")
    attached = running_session(store, project.id, "eng-attached")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="orphan"]', timeout=5000)

    stop = projects_page.locator('.dlg-choice[data-choice="kill_sessions"]')
    assert stop.is_enabled(), stop.inner_text()
    assert attached in projects_page.locator("#dlg-delete-live").inner_text()
    assert console.messages == []


# ----- defect 6: duplicate names, and a dialog titled by name alone ----------


def test_the_delete_dialog_names_the_project_by_more_than_its_name(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 6 (MEDIUM).** `create_project` is deliberately never keyed by
    name (E1). Two projects called `twin` therefore sit in the list
    distinguishable only by "0 repos" and "no activity yet", and the delete
    dialog read "Delete twin" — no id, no description, nothing on screen saying
    which of the two the button destroys.
    """
    made = seed_several_projects(store)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')

    # The list disambiguates the two rows that share a name, and only those.
    ids = projects_page.locator('.proj-row:has(.proj-name:text-is("twin")) .proj-id')
    assert ids.count() == 2, ids.all_inner_texts()
    shown = set(ids.all_inner_texts())
    assert shown == {made["twin_a"], made["twin_b"]}, shown
    assert (
        projects_page.locator(
            '.proj-row:has(.proj-name:text-is("payments")) .proj-id'
        ).count()
        == 0
    )

    projects_page.click(f'.proj-row[data-project-id="{made["twin_b"]}"]')
    projects_page.wait_for_selector("#proj-detail .proj-title", timeout=5000)
    projects_page.click("#proj-delete")
    projects_page.wait_for_selector("#dlg-delete[open]", timeout=5000)

    identity = projects_page.locator("#dlg-delete-identity").inner_text()
    assert made["twin_b"] in identity, identity
    assert made["twin_a"] not in identity, identity
    assert console.messages == []


def test_a_duplicate_name_is_warned_about_before_a_second_project_is_made(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The other half of defect 6: the create side.

    A second project of the same name is a real intent the store supports, so
    this is a warning and not a refusal — the first Create says what is about
    to happen, the second one does it. Nothing is written by the first click,
    which is the assertion that makes it a warning rather than a message shown
    after the fact.
    """
    store.create_project(name="payments", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')

    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "payments")
    projects_page.click("#p-save")

    refusal = projects_page.locator("#p-refusal")
    refusal.wait_for(timeout=5000)
    assert "already a project named" in refusal.inner_text(), refusal.inner_text()
    assert len([r for r in store.list_workspaces() if r.name == "payments"]) == 1

    projects_page.click("#p-save")

    projects_page.wait_for_selector("#dlg-project[open]", state="detached", timeout=5000)
    assert len([r for r in store.list_workspaces() if r.name == "payments"]) == 2
    assert console.messages == []


# ----- defect 7: the double submit that ended on a raw ULID ------------------


def test_a_second_delete_click_cannot_race_the_first(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 7 (MEDIUM).** Two rapid clicks: the first delete succeeded, the
    second raced it and lost, and the last sentence on screen was *"there is no
    project '<ULID>' to delete"* — a failure message, naming a raw id, about a
    delete that had worked. Non-deterministic, one run in two.

    The in-flight guard is asserted on the wire rather than on the text: the
    claim is that the second click issues no second request at all.
    """
    project = store.create_project(name="payments", description=None)
    ended_session(store, project.id, "eng-done")
    posted: list[str] = []
    projects_page.on(
        "request",
        lambda request: posted.append(request.url)
        if request.method == "POST" and "/delete" in request.url
        else None,
    )
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")

    choice = projects_page.locator('.dlg-choice[data-choice="delete"]')
    choice.dispatch_event("click")
    choice.dispatch_event("click")

    projects_page.wait_for_selector("#dlg-delete-outcome", timeout=5000)
    assert len(posted) == 1, posted
    assert store.get_workspace(project.id) is None
    assert console.messages == []


# ----- defect 10: a whitespace-only name returned silently -------------------


def test_a_whitespace_only_name_is_refused_with_a_sentence(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 10 (LOW).** `required` is satisfied by a space, so the browser
    let the form submit; `onProjectSubmit` then trimmed it to `""` and returned
    with no message at all. A control that accepts a click and says nothing is
    the one thing principle 5 forbids.
    """
    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "   ")
    projects_page.click("#p-save")

    refusal = projects_page.locator("#p-refusal")
    refusal.wait_for(timeout=5000)
    assert "needs a name" in refusal.inner_text(), refusal.inner_text()
    assert store.list_workspaces() != []
    assert [row.name for row in store.list_workspaces()] == ["Unassigned"]
    assert console.messages == []


# ----- defect 11: an ellipsised value that cannot be read at all -------------


def test_every_value_that_can_be_truncated_carries_its_full_text_as_a_title(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 11 (LOW).** QA measured a 935px repo path in a 334px box and a
    1366px title in a 266px one, neither carrying a `title` attribute — so the
    ellipsised half of a §13 allowlist path could not be read at all, by any
    means the page offered.

    A `title` is the cheapest thing that is *not* a second layout: it needs no
    width, it survives a phone, and it is the same string the element already
    holds. The assertion is `title == textContent` on every candidate, so a
    later element that truncates and forgets is caught by the same line.
    """
    long_path = (
        "/srv/engineering/platform/monorepo/services/billing/"
        "invoice-reconciliation-worker/vendor/third-party/acme-payments-sdk-fork"
    )
    project = store.create_project(
        name="platform-billing-reconciliation-worker-and-its-friends", description=None
    )
    store.add_repo(
        workspace_id=project.id,
        root_path=long_path,
        name="acme-payments-sdk-fork",
        git_common_dir=f"{long_path}/.git",
        vcs_remote=None,
    )
    session_id = running_session(store, project.id, "eng-long")
    store.apply_title(
        session_id,
        "Please take the invoice reconciliation worker and make it idempotent "
        "under at-least-once delivery from the upstream broker",
        "engine",
    )
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_project(projects_page, "platform-billing-reconciliation-worker-and-its-friends")

    mismatched = projects_page.evaluate(
        """() => {
          const selectors = ['.proj-name', '.proj-title', '.path-text', '.mini-title'];
          const bad = [];
          for (const selector of selectors) {
            for (const node of document.querySelectorAll('#page-projects ' + selector)) {
              const text = node.textContent.trim();
              if (text !== '' && node.getAttribute('title') !== text) {
                bad.push(selector + ': ' + JSON.stringify(node.getAttribute('title')));
              }
            }
          }
          return bad;
        }"""
    )
    assert mismatched == [], mismatched
    assert console.messages == []


# ============================================================================
# The second QA remediation pass (same workflow, re-run after the first).
#
# Eleven defects closed; two more found on ground the first pass had only just
# made reachable. Both are below, each naming the defect it closes.
# ============================================================================


@pytest.fixture()
def the_kill_raises(store: Store, projects_root: Path) -> None:
    """Re-register the project verbs behind a kill that **raises**.

    Three outcomes are possible from `_kill_running` and the suite could only
    reach two of them. `web/conftest.py`'s `refuses_every_kill` returns `False`
    (a stop that did not land and said so); `kills_the_owned_one` returns `True`
    for one session (a stop that landed). Neither produces a `kill_failures`
    row, and `kill_failures` is populated **only** by the raising branch —
    which is the branch `runner/local.py` actually takes for a stale handle:
    a row whose `ended_at` is still NULL while its tmux pane is gone.

    The reason string is the shape QA measured off the wire, argv and all.
    """
    from shepherd.core.runner import RunnerRefusal
    from shepherd.toolsurface.registry import reset_registry
    from shepherd.toolsurface.tools_m1 import register_read_tools
    from shepherd.toolsurface.tools_projects import register_project_tools

    from chokepoint_fixture import install_test_chokepoint

    def kill(session_id: str) -> bool:
        raise RunnerRefusal(KILL_ARGV_REASON)

    reset_registry()
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_project_tools(
        store=store, kill=kill, publish=lambda event: None, now=lambda: NOW
    )


#: The tmux argv a real `RunnerRefusal` carries. It is long on purpose: the
#: defect's second half is that the page must render it *readably* rather than
#: ellipsising the half that names the socket.
KILL_ARGV_REASON = (
    "tmux exited 1 for ['tmux', '-L', 'shepherd-runner', 'kill-session', "
    "'-t', 'shp_eng_owned']: error connecting to "
    "/tmp/tmux-0/shepherd-runner (No such file or directory)"
)


def test_a_stop_that_refused_names_the_session_and_says_why(
    projects_page: Page, store: Store, the_kill_raises: None, console: Console
) -> None:
    """**Defect 1 of the second pass (HIGH).** The server says *why* a stop did
    not take, and the page threw the answer away.

    `delete_outcome` projects eleven keys. QA counted the page's readers of each
    and found exactly one with none: `kill_failures`. So the dialog said *"2
    session(s) in this project are still running and were not stopped; nothing
    was deleted"* over a record that also held a `RunnerRefusal` naming the
    session and the socket that was not there. `bump_anomaly(STOP_FAILED)` had
    already fired — the failure was recorded everywhere except where a person
    would look.

    The assertion is on the **reason text in full**, not on its presence: the
    string carries a tmux argv, and a fix that ellipsised it would satisfy a
    "contains the session id" check while losing the part that answers the
    question.
    """
    project = store.create_project(name="payments", description=None)
    owned = owned_session(store, project.id, "eng-owned")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="kill_sessions"]', timeout=5000)

    projects_page.click('.dlg-choice[data-choice="kill_sessions"]')

    projects_page.wait_for_selector("#dlg-delete-body:has-text('were not stopped')", timeout=5000)
    live = projects_page.locator("#dlg-delete-live").inner_text()
    assert "Not stopped, and why:" in live, live
    assert owned in live, live
    assert f"RunnerRefusal: {KILL_ARGV_REASON}" in live, live
    # The project survives, which is what makes the reason worth reading.
    assert store.get_workspace(project.id) is not None
    assert console.messages == []


def test_a_second_create_click_cannot_make_a_second_project(
    projects_page: Page, store: Store, console: Console
) -> None:
    """**Defect 2 of the second pass (MEDIUM).** Defect 7's failure class, fixed
    on the delete side and left on the create side.

    `inFlight` shipped with **one** key — `delete` — and `onProjectSubmit` never
    consulted it. The duplicate-name warning does not save it: both POSTs leave
    before the list is re-read, so `view.projects` never holds the first project
    when the second is decided. QA measured `posts: 2, rows: 2` on three of
    three attempts — a *durable wrong row*, which is what separates this handler
    from the four other unguarded ones (their verbs are idempotent).

    Asserted on the wire as well as in the store: one click, one request.
    """
    posted: list[str] = []
    projects_page.on(
        "request",
        lambda request: posted.append(request.url)
        if request.method == "POST" and request.url.endswith("/api/projects")
        else None,
    )
    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "payments")
    projects_page.fill("#p-desc", "the api")

    projects_page.locator("#p-save").dblclick()

    projects_page.wait_for_selector('.proj-name:text-is("payments")', timeout=5000)
    projects_page.wait_for_timeout(500)
    made = [row for row in store.list_workspaces() if row.name == "payments"]
    assert len(posted) == 1, posted
    assert len(made) == 1, [row.name for row in store.list_workspaces()]
    assert console.messages == []


@pytest.fixture()
def the_kill_ends_the_session_then_raises(store: Store, projects_root: Path) -> None:
    """The narrow cell where a `kill_failures` row rides a **successful** delete.

    A kill that raises normally leaves `ended_at` NULL, so `commit_project_delete`
    re-derives a still-running project and refuses — which is why the refusal
    branch is where the reason is usually read. But the raise can come *after*
    the session has gone: the pane dies, the teardown that follows it does not,
    and `RunnerRefusal` escapes over a row that is already ended. The commit
    then succeeds, and a reader wired only into the refusal branch would drop
    the one record saying a stop Shepherd issued did not land.
    """
    from shepherd.core.runner import RunnerRefusal
    from shepherd.toolsurface.registry import reset_registry
    from shepherd.toolsurface.tools_m1 import register_read_tools
    from shepherd.toolsurface.tools_projects import register_project_tools

    from chokepoint_fixture import install_test_chokepoint

    def kill(session_id: str) -> bool:
        store.apply_stop_verdict(
            session_id=session_id,
            verdict=Verdict(
                stop_reason=StopReason.USER_EXITED,
                bucket=Bucket.FINISHED,
                why="the pane went away",
                confidence=1.0,
                decided_by=DecidedBy.MECHANICAL,
                next_actions=(),
                waiting_on=None,
                missing=(),
            ),
            ended_at="2026-09-22T12:00:00.000Z",
            exit_code=None,
        )
        raise RunnerRefusal(KILL_ARGV_REASON)

    reset_registry()
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_project_tools(
        store=store, kill=kill, publish=lambda event: None, now=lambda: NOW
    )


def test_a_delete_that_succeeded_still_says_which_stop_did_not_land(
    projects_page: Page, store: Store, the_kill_ends_the_session_then_raises: None,
    console: Console
) -> None:
    """The second branch of defect 1, named rather than assumed.

    The refusal path is the common one and the test above certifies it. This
    one certifies the other: the delete goes through and the reason is still on
    screen, in `#dlg-delete-outcome` beside `destroyed` and `severed`. Without
    it the fix would be one call site proved and one call site hoped for.
    """
    project = store.create_project(name="payments", description=None)
    owned = owned_session(store, project.id, "eng-owned")
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    open_delete(projects_page, "payments")
    projects_page.click('.dlg-choice[data-choice="delete"]')
    projects_page.wait_for_selector('.dlg-choice[data-choice="kill_sessions"]', timeout=5000)

    projects_page.click('.dlg-choice[data-choice="kill_sessions"]')

    projects_page.wait_for_selector("#dlg-delete-outcome", timeout=5000)
    outcome = projects_page.locator("#dlg-delete-outcome").inner_text()
    assert store.get_workspace(project.id) is None, "the delete did go through"
    assert "Not stopped, and why:" in outcome, outcome
    assert owned in outcome, outcome
    assert f"RunnerRefusal: {KILL_ARGV_REASON}" in outcome, outcome
    assert console.messages == []


# ----- BC-1: the detail pane belongs to the last project ASKED FOR ------------
#
# The defect QA round 5 reproduced (S33, and the same settle bolted onto S19 and
# S32): `loadDetail()` wrote `view.detail` and painted from **whichever read
# resolved last**, not from the project the page had last been asked to open.
# Two reads are routinely in flight at once — `projectRow`'s click handler
# starts one and does not await it, and `submitProject`'s create branch has one
# of its own — so the pane could settle on a project the user had already
# navigated away from, and `#proj-edit`'s closure, captured at render time,
# went with it. Pressing Edit then opened the dialog on the wrong workspace and
# the draft path list never reached the clicked project's two repos.
#
# **Both tests below make the race deterministic rather than hoping for it.**
# `HOLD_MATCHING_FETCH` parks the fetches whose URL matches a pattern — the
# product's own `fetch` calls, untouched otherwise — and hands the test a
# release. That turns "the later read to resolve wins" from a 1-in-4 flake into
# a fact the test states: the stale read is released *after* the newer one has
# already painted, which is the losing interleaving every time.
#
# **They assert on the DIALOG, not only on the pane.** The pane's title proves
# the render; `#p-name` and `#p-paths` prove what `#proj-edit`'s closure was
# bound to. A fix that ordered the reads but left a stale closure on the button
# would pass the first assertion and fail the second.

#: Installed into the page before the race. `real.call(window, ...)` and not
#: `real(...)`: a detached `fetch` reference is an illegal invocation in
#: chromium. `__delivered` counts released responses so the test waits on a
#: fact rather than on a duration.
HOLD_MATCHING_FETCH = """(pattern) => {
  const real = window.fetch;
  const held = [];
  const expression = new RegExp(pattern);
  window.__held = held;
  window.__delivered = 0;
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!expression.test(url)) {
      return real.call(window, input, init);
    }
    return new Promise((resolve, reject) => {
      held.push(() =>
        real.call(window, input, init).then(
          (response) => { window.__delivered += 1; resolve(response); },
          (error) => { window.__delivered += 1; reject(error); }
        )
      );
    });
  };
  window.__release = () => {
    const queued = held.splice(0, held.length);
    for (const send of queued) { send(); }
    return queued.length;
  };
}"""


def hold_fetches(page: Page, pattern: str) -> None:
    page.evaluate(HOLD_MATCHING_FETCH, pattern)


def release_and_settle(page: Page, expected: int) -> None:
    """Release the parked reads and wait for the page to be quiet again.

    The settle is `networkidle` and it is sound **on this page specifically**:
    §12 forbids polling and the product runs no timers at all, so "nothing in
    flight" is a resting state rather than a gap between ticks. It is needed
    because the assertions that follow are negative — that the stale read
    changed *nothing* — and a negative needs a point after which nothing more
    can happen.
    """
    assert page.evaluate("() => window.__release()") == expected
    page.wait_for_function(
        "(n) => window.__delivered === n", arg=expected, timeout=5000
    )
    page.wait_for_load_state("networkidle")


def seed_two_repos(store: Store, project_id: str) -> list[str]:
    paths = [f"/code/acme/{project_id}-api", f"/code/acme/{project_id}-worker"]
    for path in paths:
        store.add_repo(
            workspace_id=project_id,
            root_path=path,
            name=path.rsplit("/", 1)[-1],
            git_common_dir=f"{path}/.git",
            vcs_remote=None,
        )
    return paths


def test_a_row_clicked_while_a_create_settles_keeps_the_pane_on_the_clicked_row(
    projects_page: Page, store: Store, console: Console
) -> None:
    """BC-1, the interleaving QA round 5 hit: click a row while a create settles.

    `submitProject`'s create branch closes the dialog and only *then* reads the
    new project's detail, so a row clicked in that window starts a second read.
    The create's read is the one issued later, so serialising by request order
    would not save it either — the page has to honour the **intent** (`openId`,
    set synchronously at the click) and drop a read that no longer matches it.
    """
    payments = store.create_project(name="payments", description=None)
    seed_two_repos(store, payments.id)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    projects_page.wait_for_selector("#proj-list .proj-row")

    # Park the *new* project's detail read — every detail URL but payments'.
    hold_fetches(projects_page, f"/api/projects/(?!{payments.id}$)[^/?]+$")

    projects_page.click("#proj-new")
    projects_page.fill("#p-name", "billing")
    projects_page.click("#p-save")
    projects_page.wait_for_function(
        "() => document.getElementById('dlg-project').open === false", timeout=5000
    )
    # The create's own `loadDetail(newId)` is now issued and parked.
    projects_page.wait_for_function("() => window.__held.length === 1", timeout=5000)

    projects_page.click(f'#proj-list .proj-row[data-project-id="{payments.id}"]')
    projects_page.wait_for_selector(
        '#proj-detail .proj-title:text-is("payments")', timeout=5000
    )

    release_and_settle(projects_page, 1)

    assert projects_page.locator("#proj-detail .proj-title").inner_text() == "payments"
    projects_page.click("#proj-edit")
    projects_page.wait_for_selector("#dlg-project[open]", timeout=5000)
    assert projects_page.input_value("#p-name") == "payments"
    projects_page.wait_for_function(
        "() => document.querySelectorAll('#p-paths .path').length === 2", timeout=5000
    )
    assert console.messages == []


def test_a_detail_read_that_resolves_after_a_newer_click_paints_nothing(
    projects_page: Page, store: Store, console: Console
) -> None:
    """The same defect with no create anywhere near it — row to row.

    The variant matters because it fixes the ordering the other way round: here
    the **stale** read is the one issued first and the fresh one second, so a
    guard that only taught `submitProject` to behave would leave this red. Two
    ordinary row clicks in quick succession are enough, which is what makes
    this a user-reachable bug and not a dialog artefact.
    """
    payments = store.create_project(name="payments", description=None)
    seed_two_repos(store, payments.id)
    billing = store.create_project(name="billing", description=None)
    projects_page.reload()
    projects_page.click('.nav-item[data-page="projects"]')
    projects_page.wait_for_selector("#proj-list .proj-row")

    hold_fetches(projects_page, f"/api/projects/{payments.id}$")

    projects_page.click(f'#proj-list .proj-row[data-project-id="{payments.id}"]')
    projects_page.wait_for_function("() => window.__held.length === 1", timeout=5000)
    projects_page.click(f'#proj-list .proj-row[data-project-id="{billing.id}"]')
    projects_page.wait_for_selector(
        '#proj-detail .proj-title:text-is("billing")', timeout=5000
    )

    release_and_settle(projects_page, 1)

    assert projects_page.locator("#proj-detail .proj-title").inner_text() == "billing"
    projects_page.click("#proj-edit")
    projects_page.wait_for_selector("#dlg-project[open]", timeout=5000)
    assert projects_page.input_value("#p-name") == "billing"
    # Not `.path === 0` — that is true before the read as well, so it would pass
    # on a draft list that never loaded. The sentence only exists once
    # `renderDraftPaths` has run on an empty answer.
    projects_page.wait_for_function(
        "() => document.getElementById('p-paths').innerText.includes('No paths yet')",
        timeout=5000,
    )
    assert console.messages == []
