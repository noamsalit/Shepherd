"""Waves 6-7 UI kit — shared helpers, **no scenarios** (it collects zero tests).

STAGE B's write surface is `test_wave6_*` / `test_wave7_*` files only, so the
helpers the six wave-6/7 UI modules share live in this one module rather than
in a new shared file (BUILDING.md §7). Nothing here is a user action except the
thin Playwright wrappers at the bottom, and every one of those is a real
Playwright click, keypress, tap, hover or mouse move — never a JS-synthesised
event (test-plan §0 row "fetch shim"; browser.py). Every `evaluate` below is a
**read**: computed styles, boxes, `document.activeElement`, attribute values.

Two kinds of wait, never a sleep as readiness:

* `settle(...)` — a UI change the user's own input causes. Its bound
  (`UI_BOUND_S`) is a harness liveness bound: the caller decides whether a
  blown one is FAIL (a same-channel control qualified it) or BLOCKED.
  `settle`, `pump` and `UI_BOUND_S` are `browser.py`'s (re-exported here for
  the wave-6/7 modules that import them from this kit).
* `await_env(...)` — the page or the instance being up at all.

Screenshots go to `<run_dir>/ui/<scenario>/<label>.png` (the same directory
`browser.BrowserSession.context` writes its end-of-context `pageN.png` and
`pagelog.json` into), so the report links one directory per scenario.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .. import tmuxctl
from ..bootstrap import git
from ..browser import UI_BOUND_S as UI_BOUND_S
from ..browser import PageLog, visible_roots
from ..browser import pump as pump
from ..browser import settle as settle
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld, Helper, db_rows
from ..pool import InstancePool
from ..sandbox import RunContext
from ..sessions import await_session, now_ms, session_row, sidecar, write_sidecar
from ..verdict import Blocked, await_env

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Locator, Page, Request

#: The page's first paint: document, modules, the first reads and the stream.
LOAD_BOUND_S = 15.0

#: The six roots in the order the nav lists them, with their nav ids and texts
#: (index.html; app.js `NAV`). The text is what `#topbar-title` must equal.
ROOTS: tuple[str, ...] = ("shepherd", "flock", "queues", "projects", "kanban", "settings")
NAV_ID: Mapping[str, str] = {
    "shepherd": "nav-chat", "flock": "nav-fleet", "queues": "nav-queues",
    "projects": "nav-projects", "kanban": "nav-kanban", "settings": "nav-settings",
}
NAV_TEXT: Mapping[str, str] = {
    "shepherd": "Shepherd", "flock": "Flock", "queues": "Queues",
    "projects": "Projects", "kanban": "Kanban", "settings": "Settings",
}

#: Product sentences (cited where the plan cites them).
UNREACHABLE = "The request did not reach the server — Shepherd may not be running."  # app.js:71, projects.js:50, chat.js:131
SETTINGS_UNREACHABLE = (  # settings.js:209-211
    "The request did not reach the server — Shepherd may not be running, so these numbers are whatever was last read."
)
QUEUES_STUB = "Not built this milestone. Work sources are W3."  # index.html:328
KANBAN_STUB = "Not built this milestone."  # index.html:347
READ_ONLY_BANNER = "read-only — this session wasn't started here. Open it in the platform to get a terminal."  # session.js:36


def url(port: int, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{port}/"


# ----- reads (evaluate = read-only queries) ------------------------------------------


def text_of(locator: Locator) -> str:
    return locator.inner_text().strip()


def attr(locator: Locator, name: str) -> str | None:
    return locator.get_attribute(name)


@dataclass(frozen=True)
class NavState:
    roots: list[str]
    current: list[str]
    title: str

    def as_json(self) -> dict[str, object]:
        return {"roots": self.roots, "current": self.current, "title": self.title}


def nav_state(page: Page) -> NavState:
    current = page.evaluate(
        "() => [...document.querySelectorAll('.nav-item')]"
        ".filter(e => e.getAttribute('aria-current') === 'page').map(e => e.id)"
    )
    return NavState(
        roots=visible_roots(page),
        current=[str(item) for item in current] if isinstance(current, list) else [],
        title=page.locator("#topbar-title").inner_text().strip(),
    )


def is_showing(page: Page, name: str) -> bool:
    state = nav_state(page)
    return state.roots == [f"page-{name}"] and state.current == [NAV_ID[name]] and state.title == NAV_TEXT[name]


def box(locator: Locator) -> dict[str, float] | None:
    found = locator.bounding_box()
    if found is None:
        return None
    return {"x": float(found["x"]), "y": float(found["y"]), "width": float(found["width"]), "height": float(found["height"])}


def viewport(page: Page) -> tuple[int, int]:
    size = page.viewport_size
    if size is None:
        raise Blocked("the page has no viewport size")
    return int(size["width"]), int(size["height"])


def computed(locator: Locator, prop: str) -> str:
    value = locator.evaluate("(e, p) => getComputedStyle(e).getPropertyValue(p)", prop)
    return str(value).strip()


def active(page: Page) -> dict[str, str]:
    """`document.activeElement`: id, tag, and the data keys the plan names."""
    value = page.evaluate(
        "() => { const a = document.activeElement; if (!a) return {};"
        " const r = a.getBoundingClientRect();"
        " return {id: a.id || '', tag: a.tagName.toLowerCase(), cls: typeof a.className === 'string' ? a.className : '',"
        " in_pane: a.closest('nav.pane') ? 'yes' : 'no', right: String(r.right), left: String(r.left),"
        " session: a.dataset ? (a.dataset.sessionId || '') : '', project: a.dataset ? (a.dataset.projectId || '') : '',"
        " bucket: a.dataset ? (a.dataset.bucket || '') : '', text: (a.innerText || '').slice(0, 80)}; }"
    )
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def dialog_open(page: Page, selector: str) -> bool:
    return bool(page.locator(selector).evaluate("d => d.open === true"))


def document_text(page: Page) -> str:
    return str(page.evaluate("() => document.body.innerText"))


def scroll_overflow(page: Page) -> tuple[int, int]:
    value = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    if isinstance(value, list) and len(value) == 2:
        return int(value[0]), int(value[1])
    raise Blocked("could not read scrollWidth/innerWidth")


def xss_fired(page: Page) -> object:
    return page.evaluate("() => window.__xss")


# ----- waits: `settle` / `pump` are browser.py's (re-exported above) -------------------


def api_since(log: PageLog, start: int, method: str | None = None) -> list[str]:
    """`METHOD path` for every `/api/` request logged at index >= start."""
    found: list[str] = []
    for entry in log.requests[start:]:
        request_url = entry["url"]
        if "/api/" not in request_url:
            continue
        if method is not None and entry["method"] != method:
            continue
        found.append(f"{entry['method']} /api/{request_url.split('/api/', 1)[1]}")
    return found


def posts_to(log: PageLog, start: int, fragment: str) -> list[str]:
    return [line for line in api_since(log, start, "POST") if fragment in line]


# ----- the page ----------------------------------------------------------------------------


def open_app(context: BrowserContext, port: int, *, wait_live: bool = True, host: str = "127.0.0.1") -> Page:
    """A new tab on the app, landed on Shepherd, with the Flock's first paint done."""
    page = context.new_page()
    page.goto(url(port, host), wait_until="load")
    # Not "exactly one root": that is U1's assertion, and a mutation proving it
    # bites must be able to reach it. Here: the shell's own route ran.
    await_env(lambda: (page.locator("#nav-chat").get_attribute("aria-current") == "page"
                       and "page-shepherd" in visible_roots(page)) or None,
              LOAD_BOUND_S, "the app's first paint (Shepherd routed)")
    # The Flock's first read painted: a project button, or (no session anywhere —
    # fleet_tree lists no workspace) F16's empty state.
    await_env(lambda: (page.locator("#flock-projects .project").count() > 0
                       or page.locator("#empty-state").get_attribute("hidden") is None) or None, LOAD_BOUND_S,
              "the Flock's first read painted (a project button or the empty state)")
    if wait_live:
        await_env(lambda: text_of(page.locator("#stream-status")) == "live" or None, LOAD_BOUND_S,
                  "#stream-status reads live")
    return page


class Shots:
    """Named screenshots for one scenario, into `<run_dir>/ui/<sid>/`."""

    def __init__(self, artifacts: Path, sid: str) -> None:
        self.directory = artifacts / sid
        self.directory.mkdir(parents=True, exist_ok=True)
        self.taken: list[str] = []

    def __call__(self, page: Page, label: str, full_page: bool = False) -> str:
        target = self.directory / f"{label}.png"
        page.screenshot(path=str(target), full_page=full_page)
        self.taken.append(target.name)
        return str(target)

    def note(self) -> str:
        return f"screenshots in {self.directory}: {', '.join(self.taken)}"


# ----- user-like input (Playwright only) ------------------------------------------------------


def nav_click(page: Page, name: str) -> None:
    page.locator(f"#{NAV_ID[name]}").click()


def drawer_nav(page: Page, name: str, *, touch: bool) -> None:
    """At <= the shell breakpoint the nav is in the drawer: open it, then pick."""
    opener = page.locator("#drawer-open")
    if touch:
        opener.tap()
    else:
        opener.click()
    await_env(lambda: page.locator("#shell").get_attribute("data-drawer") == "open" or None, UI_BOUND_S,
              "the drawer opened")
    item = page.locator(f"#{NAV_ID[name]}")
    await_env(lambda: (b := box(item)) is not None and b["x"] >= 0 or None, UI_BOUND_S,
              "the drawer finished sliding in (nav item on screen)")
    if touch:
        item.tap()
    else:
        item.click()


def go(page: Page, name: str, *, drawer: bool, touch: bool = False) -> None:
    if drawer:
        drawer_nav(page, name, touch=touch)
    else:
        nav_click(page, name)
    await_env(lambda: is_showing(page, name) or None, UI_BOUND_S, f"the {name} root is showing after its nav")


def press_tab_until(page: Page, match: Callable[[dict[str, str]], bool], limit: int = 60,
                    key: str = "Tab") -> int | None:
    """Press Tab until the focused element matches; the number of presses, or None."""
    for count in range(1, limit + 1):
        page.keyboard.press(key)
        if match(active(page)):
            return count
    return None


def tap_or_click(locator: Locator, touch: bool) -> None:
    if touch:
        locator.tap()
    else:
        locator.click()


# ----- instance seeding (through the product's front door) ------------------------------------


@dataclass
class Attached:
    helper: Helper
    body: dict[str, object]
    session_id: str

    @property
    def engine_id(self) -> str:
        return str(self.body["sessionId"])


def attach(pool: InstancePool, controld: Controld, cwd: Path, name: str, *, status: str = "busy",
           waiting_for: str | None = None, status_age_s: float = 0.0, started_age_s: float = 0.0,
           state: str | None = None, bound_s: float = 10.0) -> Attached:
    """A harness helper process plus its sidecar (a harness-shaped input, sessions.py; G5)."""
    helper = pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(cwd), status=status, name=name,
                   waiting_for=waiting_for, status_age_s=status_age_s, started_age_s=started_age_s)
    write_sidecar(controld.root.sessions, body)
    row = await_session(controld, str(body["sessionId"]), bound_s, state=state)
    return Attached(helper=helper, body=body, session_id=str(row["id"]))


def rewrite(controld: Controld, attached: Attached, **changes: object) -> None:
    """A newer sidecar for the same process: a real writer bumps its stamps."""
    updated = dict(attached.body)
    updated.update(changes)
    stamp = now_ms()
    updated["updatedAt"] = stamp
    updated["statusUpdatedAt"] = stamp
    write_sidecar(controld.root.sessions, updated)
    attached.body = updated


def new_repo(parent: Path, name: str) -> Path:
    """A one-commit git repo inside this module's own instance root (never shared)."""
    path = parent / name
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", str(path))
    (path / "README.md").write_text(f"{name}\n", encoding="utf-8")
    git("-C", str(path), "add", "README.md")
    git("-C", str(path), "commit", "-q", "-m", f"{name}: initial")
    return path


def create_project(client: Client, name: str, description: str | None = None) -> str:
    answer = client.create_project(name, description)
    project = answer.get("project")
    if answer.get("created") is not True or not isinstance(project, dict):
        raise Blocked(f"create_project({name!r}) did not create: {answer!r}")
    return str(project["project_id"])


def add_repo(client: Client, project_id: str, path: Path) -> str:
    answer = client.add_repo(project_id, str(path))
    repo = answer.get("repo")
    if answer.get("added") is not True or not isinstance(repo, dict):
        raise Blocked(f"add_repo({path}) did not add: {answer!r}")
    return str(repo["repo_id"])


def spawn_owned(client: Client, project_id: str, cwd: Path, title: str) -> str:
    """`POST /api/sessions` (spawn_session, the O1 route) with the fake engine on PATH."""
    response = client.post("/api/sessions", {"workspace_id": project_id, "cwd": str(cwd), "title": title})
    data = response.data()
    if data.get("spawned") is not True or not isinstance(data.get("session_id"), str):
        raise Blocked(f"spawn_session did not spawn {title!r}: {data!r}")
    return str(data["session_id"])


def kill_owned(client: Client, session_id: str) -> dict[str, object]:
    return client.post(f"/api/sessions/{session_id}/kill", {}).data()


def pane_alive(run: RunContext, k: int, session_id: str) -> bool:
    """Our tmux server on this instance's socket still has the session's pane."""
    return f"shepherd_{session_id}" in tmuxctl.sessions(run.runner_socket(k), run.pid)


def capture_pane(run: RunContext, k: int, session_id: str) -> str:
    done = tmuxctl.run(run.runner_socket(k), run.pid, "capture-pane", "-p", "-t",
                       tmuxctl.target(f"shepherd_{session_id}"), check=False)
    return done.stdout


def send_line(run: RunContext, k: int, session_id: str, text: str) -> None:
    """The harness types a line into the fake engine's pane (its `cat` echoes it)."""
    tmuxctl.run(run.runner_socket(k), run.pid, "send-keys", "-t", tmuxctl.target(f"shepherd_{session_id}"),
                "-l", text)
    tmuxctl.run(run.runner_socket(k), run.pid, "send-keys", "-t", tmuxctl.target(f"shepherd_{session_id}"), "Enter")


def session_api(client: Client, session_id: str) -> dict[str, object]:
    answer = client.session(session_id)
    return as_dict(answer.get("session")) if answer.get("found") is True else {}


def tree_sessions(client: Client, project_id: str) -> list[dict[str, object]]:
    for workspace in as_list(client.fleet_tree().get("workspaces")):
        entry = as_dict(workspace)
        if entry.get("project_id") == project_id:
            return [as_dict(row) for row in as_list(entry.get("sessions"))]
    return []


def project_rows(controld: Controld, name: str) -> list[dict[str, object]]:
    return db_rows(controld.db, "SELECT id, name, description FROM workspace WHERE name = ?", (name,))


def session_title(controld: Controld, session_id: str) -> dict[str, object]:
    rows = db_rows(controld.db, "SELECT title, title_source FROM session WHERE id = ?", (session_id,))
    return rows[0] if rows else {}


def engine_row(controld: Controld, engine_id: str) -> dict[str, object] | None:
    return session_row(controld, engine_id)


def js_number(value: object) -> str:
    """`String(n)` as the page's template literal prints a JSON number."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


@dataclass
class PostBodies:
    """The JSON bodies of POSTs the page sent (a Playwright `request` listener)."""

    bodies: list[tuple[str, object]] = field(default_factory=list)

    def of(self, fragment: str) -> list[object]:
        return [body for path, body in self.bodies if fragment in path]


def record_posts(page: Page) -> PostBodies:
    sink = PostBodies()

    def on_request(request: Request) -> None:
        if request.method != "POST":
            return
        raw = request.post_data
        request_url = request.url
        try:
            decoded: object = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            decoded = raw
        sink.bodies.append((request_url, decoded))

    page.on("request", on_request)
    return sink


def wait_until(predicate: Callable[[], bool], bound_s: float, what: str) -> float:
    """Environment liveness with an elapsed time (for a control's latency)."""
    started = time.monotonic()
    await_env(lambda: predicate() or None, bound_s, what)
    return max(time.monotonic() - started, 1e-3)


def names(items: Sequence[object]) -> list[str]:
    return [str(item) for item in items]
