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
    """
    project = store.create_project(name="payments", description=None)
    live = running_session(store, project.id, "eng-live")
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
    register_project_tools(store=store, kill=kill, now=lambda: NOW)
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
    """
    project = store.create_project(name="payments", description=None)
    owned = running_session(store, project.id, "eng-owned")
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
