"""T10.1 — `tools/render_check.py` driven over a **real `controld`**, and the
twelve screenshots a person looks at.

**Why this module exists at all.** The integration pass drove the shipped
`index.html` over a real `controld` and got *12 pages · 12 screenshots ·
0 failures* — from a **scratchpad driver**, which it said plainly was evidence
nobody could re-run. `docs/probes/`'s standing rule is the one applied here: a
capture is worth keeping because **re-running the probe reproduces it**. So the
driver is committed, and the screenshots are its output rather than an artefact
somebody kept.

**What is real here, named because that is the whole claim.** The process is
the shipped `controld` composition root — the real store migrated on disk, the
real tool surface frozen before the bind, the real discovery loop, and the real
`ThreadingHTTPServer` on an ephemeral loopback port. The page is the shipped
`src/shepherd/web/static/index.html` fetched from `/`; the modules come off
`/static/` from that server; the rows are written through the shipped `Store`.
The browser is chromium at 390×844 and 1280×900. The only thing this test
supplies is the clicks, and it does not even supply those — `render_check.check`
does.

**Where the screenshots land:** `scratchpad/render-live/shots/` in the repo,
twelve files named `<viewport>-<page>.png`. The path is printed by the run and
asserted below, because "the human checkpoint is a directory nobody can find"
is the same defect as no checkpoint at all. `scratchpad/` is ignored by git:
the *driver* is the committed evidence, the pixels are derived from it.

**Three mechanics inherited rather than rediscovered.**

1. `controld` refuses to start (`SocketPathTooLong`) when `XDG_RUNTIME_DIR` sits
   under a long path: the abstract-socket budget is 107 bytes and a scratchpad
   path alone can spend 88 of it. **Only** the runtime dir is redirected to a
   short throwaway; data, config, state and cache stay in `tmp_path`, and the
   assertion that every resolved directory is inside one of the two is kept —
   a short path bought by escaping the throwaway would be worse than the
   refusal.
2. `playwright` is **not** a declared dependency (`pyproject.toml` names
   `claude-agent-sdk` and `anyio`), so `pytest.importorskip` is the **first
   executable statement** of this module. `-m 'not live'` cannot save it:
   marker deselection happens *after* collection has already imported the file.
3. `tools/` is on no import path (`pythonpath = ["src"]`), so the tool is loaded
   by path — registered in `sys.modules` **before** `exec_module`, or it cannot
   define a dataclass, and unregistered again if `exec_module` raises, or the
   next importer is handed a half-initialised module.

**What this does not prove** is written at the bottom of the module, next to the
test that ends the run, because it is the last gate before a person looks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright")

import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

from shepherd.core.states import Origin, Ownership
from shepherd.daemons import controld
from shepherd.host.detect import detect_host

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_CHECK = REPO_ROOT / "tools" / "render_check.py"

#: The human checkpoint. Stable, printed, and asserted to hold twelve files.
SHOTS = REPO_ROOT / "scratchpad" / "render-live" / "shots"

#: Every environment variable any `HostPlatform` driver reads to place its
#: directories — the same tuple `tests/daemons/test_controld.py` redirects, for
#: the same reason: `LinuxHost` takes the `XDG_*` family and `MacHost` takes
#: `HOME`/`TMPDIR`, and a fixture that redirects one family hands the *other*
#: platform the developer's real home.
HOST_DIR_ENV: tuple[str, ...] = (
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "HOME",
    "TMPDIR",
)


def load_render_check() -> ModuleType:
    """The tool, by path — `tools/` is importable from nowhere.

    Both halves of the recipe, copied from
    `tests/tools/test_render_check_args.py` with its reasons: registered before
    execution so `dataclasses` can resolve `Args`' annotations through
    `sys.modules[cls.__module__]`, and unregistered on failure so a module that
    raised half-way is not handed to the next importer as though it had loaded.
    """
    spec = importlib.util.spec_from_file_location("render_check", RENDER_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[spec.name]
        raise
    return module


rc = load_render_check()


def settings_digest() -> str:
    """P13: the real `~/.claude/settings.json`, hashed. Read-only."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    path = (Path(configured) if configured else Path.home() / ".claude") / "settings.json"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return "absent"


# ---------------------------------------------------------------------------
# The negative control: a page laid out below the fold, and its twin that is not
# ---------------------------------------------------------------------------

#: A shell the checker accepts, with one page's root switchable between the
#: healthy layout and the two shapes the viewport gate exists to catch.
#:
#: `href="data:,"` is load-bearing: without it chromium fetches `/favicon.ico`,
#: gets a 404 and logs a **console error**, which this checker correctly treats
#: as a failure — and the passing half of the control would then fail for a
#: reason that has nothing to do with layout.
#:
#: The sabotage is one declaration on one page, so a failure names one page and
#: the other five stay green. That is what makes it evidence rather than noise:
#: a page that fails for six unrelated reasons looks exactly like a working gate.
CONTROL_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>control</title>
<link rel="icon" href="data:,">
<style>
  [hidden] {{ display: none !important; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{ display: flex; flex-direction: column; }}
  main {{ flex: 1; min-height: 0; display: flex; flex-direction: column; }}
  /* Every page root fills the column it is given — which is what all six of
     the shipped roots do, and what all twelve healthy readings measure. */
  main > section {{ flex: 1; min-height: 0; }}
  #page-{broken} {{ {defect} }}
</style>
</head><body>
<button id="drawer-open" type="button">menu</button>
<nav>{nav}</nav>
<main>{views}</main>
<script type="module">
document.querySelectorAll('.nav-item').forEach((n) => {{
  n.addEventListener('click', (e) => {{
    e.preventDefault();
    const want = n.dataset.page;
    document.querySelectorAll('main > section').forEach((s) => {{
      s.hidden = s.id !== 'page-' + want;
    }});
  }});
}});
</script>
</body></html>
"""

#: The page whose root is sabotaged. Any of the six would do; the Flock is the
#: page the recorded defects were found on.
BROKEN_PAGE = "flock"

#: The three layouts, one declaration apart — which is what makes them a control
#: rather than three unrelated pages.
#:
#: `collapsed` is M7 exactly: `.main > .detail` carries `flex: 1` and every other
#: page root does too; the Shepherd page lost it and became a content-height box
#: at the top of an empty column, with the composer unpinned. `render_check.py`
#: reported twelve pages and zero failures over it.
#:
#: `below` is the containment half — a root pushed past the bottom edge, which
#: no assertion in this tool could see before either.
LAYOUTS = {
    "healthy": "",
    "collapsed": "flex: none;",
    # `position: relative` rather than a margin: a margin inside a `flex: 1`
    # item is absorbed by the flex base and the root collapses to nothing, which
    # playwright then reports as "did not open" — a different defect, and one
    # the tool could already see.
    "below": "position: relative; top: 100vh;",
}


def control_html(*, layout: str) -> str:
    nav = "".join(
        f'<a class="nav-item" data-page="{name}" href="#">{name}</a>' for name, _ in rc.PAGES
    )
    views = "".join(
        f'<section id="page-{name}" hidden><h1>{must_see}</h1></section>'
        for name, must_see in rc.PAGES
    )
    return CONTROL_TEMPLATE.format(
        nav=nav, views=views, broken=BROKEN_PAGE, defect=LAYOUTS[layout]
    )


def run_over(html: str, tmp_path: Path, name: str) -> tuple[int, str]:
    """Write a page, run the checker over it, hand back `(exit code, stdout)`."""
    import io
    from contextlib import redirect_stdout

    page = tmp_path / f"{name}.html"
    page.write_text(html, encoding="utf-8")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = rc.check(str(page), tmp_path / f"shots-{name}", must_fill=True)
    return code, buffer.getvalue()


def test_the_viewport_check_passes_a_page_laid_out_inside_the_screen(tmp_path: Path) -> None:
    """The control's passing half, run first: the fixture is otherwise clean.

    Without it the two failing halves below prove nothing — a page that fails
    for six unrelated reasons is indistinguishable from a working gate.
    """
    code, out = run_over(control_html(layout="healthy"), tmp_path, "healthy")
    assert code == 0, out
    assert "12 pages checked · 12 screenshots · 0 failures" in out, out


@pytest.mark.parametrize(
    ("layout", "complaint"),
    [("collapsed", "collapsed above the fold"), ("below", "below the fold")],
)
def test_the_viewport_check_fails_a_page_that_is_not_on_the_screen(
    tmp_path: Path, layout: str, complaint: str
) -> None:
    """A gate nobody has seen fail is not a gate — and this one has already been
    seen **not** to fail on a real defect.

    Both shapes are planted one declaration away from the passing layout above,
    and both must be named on the phone *and* on the laptop rather than merely
    somewhere: a rule that holds at one width is how `.set-panel` outranked the
    phone drill-down for a whole milestone.
    """
    code, out = run_over(control_html(layout=layout), tmp_path, layout)
    assert code == 1, out
    assert complaint in out, out
    for viewport, _width, _height in rc.VIEWPORTS:
        assert f"[{viewport}] {BROKEN_PAGE}: the page root is" in out, (viewport, out)
    # …and only the sabotaged page is named, so the failure is evidence.
    named = {line.split("] ")[1].split(":")[0] for line in out.splitlines() if line.startswith("FAIL")}
    assert named == {BROKEN_PAGE}, named


# ---------------------------------------------------------------------------
# The live drive
# ---------------------------------------------------------------------------


@pytest.fixture()
def short_runtime_dir() -> Iterator[Path]:
    """A throwaway runtime dir with a **short** path, and nothing else in it.

    `plan_socket` refuses a path over the 107-byte abstract-socket budget, and
    a pytest `tmp_path` under a deep working directory can spend most of it
    before `shepherd/shepherd-control.sock` is appended. This is the only
    directory that leaves `tmp_path`, it holds sockets and nothing durable, and
    it is removed whether the test passes or not.
    """
    root = Path(tempfile.mkdtemp(prefix="shp-", dir="/tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def live_controld(
    tmp_path: Path, short_runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[controld.Controld]:
    """The shipped composition root, on loopback, over a throwaway host."""
    targets = {
        "XDG_DATA_HOME": tmp_path / "xdg_data_home",
        "XDG_CONFIG_HOME": tmp_path / "xdg_config_home",
        "XDG_STATE_HOME": tmp_path / "xdg_state_home",
        "XDG_CACHE_HOME": tmp_path / "xdg_cache_home",
        "XDG_RUNTIME_DIR": short_runtime_dir,
        "HOME": tmp_path / "home",
        "TMPDIR": short_runtime_dir,
    }
    # The list and the redirect cannot drift: a variable added to HOST_DIR_ENV
    # and not redirected fails here rather than in whichever run first reads
    # the developer's real home.
    assert tuple(targets) == HOST_DIR_ENV
    # **Before** the redirect, not after.** Playwright resolves its browsers
    # under `$XDG_CACHE_HOME/ms-playwright` (falling back to `~/.cache`), so
    # redirecting the cache and the home directory — which this fixture must do,
    # or `controld` writes into the developer's real one — hides chromium from
    # the check that is about to run it, and the failure reads
    # `Executable doesn't exist at …/ms-playwright/…`: an environment fact
    # wearing a code defect's clothes. Pinned explicitly to where it resolves
    # *now*, and `setdefault` so an operator who set it keeps their value.
    monkeypatch.setenv(
        "PLAYWRIGHT_BROWSERS_PATH",
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        or str(Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"),
    )
    for name, target in targets.items():
        monkeypatch.setenv(name, str(target))

    engine_config_dir = tmp_path / "engine-config"
    (engine_config_dir / "sessions").mkdir(parents=True)

    dirs = detect_host().dirs()
    # Arrival, not trust. The escape assertion is kept in full even though one
    # of the two roots is now outside `tmp_path`: "inside the throwaway" is the
    # property, and it has two halves rather than one.
    allowed = (tmp_path, short_runtime_dir)
    for directory in (dirs.data_dir, dirs.config_dir, dirs.runtime_dir):
        assert any(root == directory or root in directory.parents for root in allowed), (
            f"{directory} escaped the throwaway host"
        )
    assert tmp_path in dirs.data_dir.parents, "the database must not live in /tmp"

    started = controld.start(host=detect_host(), port=0, engine_config_dir=engine_config_dir)
    try:
        yield started
    finally:
        controld.stop(started)


@pytest.mark.live
def test_every_page_renders_at_both_widths(live_controld: controld.Controld) -> None:
    """P11, against the served product — never the prototype file.

    The difference is the whole point of driving a server: a `file://` page
    proves the markup and the script, and cannot prove that the server hands
    over the same bytes, that the module graph resolves from `/static/`, or
    that the first paint survives a real API answering with real rows. Those
    are exactly the failures a local file cannot have.

    **What this does not prove**, stated here because this is the last gate
    before a person looks at the pixels:

    * not a phone's real browser, not a tunnel, not a slow network — six pages
      at two viewports in headless chromium on this host;
    * not the terminal: no owned session's WebSocket is driven;
    * not the Shepherd conversation against a real master;
    * not *correctness* of any layout — the checks are console errors, the
      `must_see` string, page-root exclusivity, horizontal overflow and now the
      viewport. A page can satisfy all five and still be ugly, mislabelled or
      wrong. That is what the twelve screenshots are for, and why this task's
      checkpoint is a human one.
    """
    before = settings_digest()

    store = live_controld.store
    workspace = store.create_project(name="shepherd", description="the orchestrator itself")
    session = store.register_session(
        engine_session_id="eng-live-1",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=str(REPO_ROOT),
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    origin = f"http://127.0.0.1:{live_controld.port}/"
    print(f"\ncontrold: {origin}")
    print(f"seeded project={workspace.id} session={session.id}")

    # Regenerable, not accumulated: a leftover PNG from an older run is a
    # screenshot of a page that no longer exists, sitting in the directory a
    # person is about to look at.
    shutil.rmtree(SHOTS, ignore_errors=True)

    code = rc.check(origin, SHOTS, fail_on_empty=True, must_fill=True)
    print(f"screenshots: {SHOTS}")

    assert code == 0
    taken = sorted(path.name for path in SHOTS.glob("*.png"))
    expected = sorted(
        f"{viewport}-{page}.png" for viewport, _w, _h in rc.VIEWPORTS for page, _m in rc.PAGES
    )
    assert taken == expected, taken
    assert len(taken) == 12, taken
    assert settings_digest() == before, "the live drive touched the real user settings"
