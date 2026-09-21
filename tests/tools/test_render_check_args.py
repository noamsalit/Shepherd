"""T0.1 — `tools/render_check.py` learns to point at a server, and the JS gate.

Two seams, both named by Phase 0 of
`docs/plans/2026-09-21-projects-and-ui-plan.md`:

* **unit** — argument handling, the `PAGES` table, and the two named selector
  constants;
* **integration** — the tool driven against a **throwaway static server** on
  loopback, once over a page it should accept and once over a page it should
  reject. A checker nobody has seen fail is not a checker.

**Import mechanics.** `pyproject.toml:53` sets `pythonpath = ["src"]`, so
`import render_check` does not work from a test. The tool is loaded by path.
There is no `tests/tools/__init__.py` — `tests/store/` has none either.

**Why the skip is the first executable statement (F13).**
`tools/render_check.py` imports `playwright.sync_api` at module level and
playwright is **not** a declared dependency of this project. Loading the tool by
path would therefore make a green suite depend on an undeclared package.
`-m 'not live'` does not save it: marker deselection happens *after* collection
has already imported this module. So the skip runs before anything else, and
`test_the_skip_guards_every_later_import` holds the line against a future edit
that quietly moves an import above it.

The second tool this task produces, `tools/js_syntax_check.py`, is exercised
**only through a subprocess**. Its third-party parser is likewise undeclared and
no file under `tests/` may name it, let alone import it (A6).
"""

import pytest

pytest.importorskip("playwright")

import ast
import importlib.util
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_CHECK = REPO_ROOT / "tools" / "render_check.py"
JS_SYNTAX_CHECK = REPO_ROOT / "tools" / "js_syntax_check.py"
PYTHON = sys.executable

#: The six pages of the redesign, in nav order (`docs/design/ui-decisions.md`).
EXPECTED_PAGES = ("shepherd", "flock", "queues", "projects", "kanban", "settings")


def load_render_check() -> ModuleType:
    """The tool, loaded by path because `tools/` is on no import path."""
    spec = importlib.util.spec_from_file_location("render_check", RENDER_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `dataclasses` resolves a field's
    # annotations through `sys.modules[cls.__module__]`, so a module built by
    # `module_from_spec` and never registered cannot define a dataclass at all.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rc = load_render_check()


# --------------------------------------------------------------------------
# A served page, built here rather than frozen as a fixture file: T0.1's
# declared Files are three, and a fixture tree is a fourth.
# --------------------------------------------------------------------------

#: `href="data:,"` is load-bearing. Without it chromium requests `/favicon.ico`,
#: the static server answers 404, and the browser logs that as a **console
#: error** — which this checker, correctly, treats as a failure. The good-page
#: test would then fail for a reason that has nothing to do with the page.
PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>fixture</title>
<link rel="icon" href="data:,">
<style>[hidden]{{display:none!important}}body{{margin:0}}</style>
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


def page_html(*, break_page: str | None = None) -> str:
    """A shell that satisfies the checker, optionally with one page sabotaged.

    `break_page` removes that page's `must_see` string and nothing else, so a
    failure names one page and the other five stay green — which is what makes
    the failure evidence rather than noise.
    """
    nav = "".join(
        f'<a class="nav-item" data-page="{name}" href="#">{name}</a>' for name, _ in rc.PAGES
    )
    views = ""
    for name, must_see in rc.PAGES:
        body = "deliberately missing" if name == break_page else must_see
        views += f'<section id="page-{name}" hidden><h1>{body}</h1></section>'
    return PAGE_TEMPLATE.format(nav=nav, views=views)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # noqa: D102 - silence the server
        return


def serve(root: Path) -> tuple[ThreadingHTTPServer, str]:
    """A throwaway static server on an ephemeral loopback port."""

    def build(*args: object, **kwargs: object) -> SimpleHTTPRequestHandler:
        return QuietHandler(*args, directory=str(root), **kwargs)  # type: ignore[arg-type]

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), build)  # type: ignore[arg-type]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    return httpd, f"http://127.0.0.1:{port}/index.html"


@pytest.fixture
def served(tmp_path: Path):
    """`(write_page, origin)` — write markup, get a URL that serves it."""
    root = tmp_path / "www"
    root.mkdir()
    httpd, origin = serve(root)
    try:
        yield (lambda html: (root / "index.html").write_text(html)), origin
    finally:
        httpd.shutdown()
        httpd.server_close()


# --------------------------------------------------------------------------
# Unit seam — the table, the constants, the argument handling
# --------------------------------------------------------------------------


def test_pages_names_the_six_pages_of_the_redesign() -> None:
    assert tuple(name for name, _ in rc.PAGES) == EXPECTED_PAGES
    for name, must_see in rc.PAGES:
        assert must_see, f"{name} has no must_see string"


def test_the_two_selectors_are_named_constants_with_one_definition_site() -> None:
    """The shell and the checker cannot drift apart silently.

    A second literal spelling of either selector anywhere in the tool is the
    drift these constants exist to prevent, so the count is asserted, not the
    mere existence of the names.
    """
    assert rc.NAV_SELECTOR.format(page="flock") == '.nav-item[data-page="flock"]'
    assert rc.DRAWER_SELECTOR == "#drawer-open"

    source = RENDER_CHECK.read_text()
    assert source.count('.nav-item[data-page=') == 1
    assert source.count('"#drawer-open"') == 1


def test_target_url_passes_a_url_through_and_resolves_a_path(tmp_path: Path) -> None:
    assert rc.target_url("http://127.0.0.1:8765/") == "http://127.0.0.1:8765/"
    assert rc.target_url("https://example.invalid/x") == "https://example.invalid/x"
    proto = tmp_path / "shepherd-dark.html"
    proto.write_text("<!doctype html>")
    assert rc.target_url(str(proto)) == proto.resolve().as_uri()


def test_the_url_flag_and_the_file_flag_both_name_a_target() -> None:
    assert rc.parse_args(["--url", "http://127.0.0.1:8765/"]).target == "http://127.0.0.1:8765/"
    assert rc.parse_args(["--file", "shepherd-dark.html"]).target == "shepherd-dark.html"
    assert rc.parse_args(["shepherd-dark.html"]).target == "shepherd-dark.html"


def test_url_and_file_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        rc.parse_args(["--url", "http://127.0.0.1:8765/", "--file", "shepherd-dark.html"])


def test_shots_land_beside_a_file_and_in_shots_for_a_url() -> None:
    assert rc.parse_args(["--url", "http://127.0.0.1:8765/"]).shots == Path("shots")
    assert rc.parse_args(["--file", "proto/x.html"]).shots == Path("proto/shots")
    assert rc.parse_args(["--url", "http://x/", "out"]).shots == Path("out")


def test_fail_on_empty_is_off_unless_asked_for() -> None:
    assert rc.parse_args(["--url", "http://x/"]).fail_on_empty is False
    assert rc.parse_args(["--url", "http://x/", "--fail-on-empty"]).fail_on_empty is True


def test_the_skip_guards_every_later_import() -> None:
    """`pytest.importorskip("playwright")` runs before anything heavy is imported.

    Asserted structurally rather than by eye: the only statements permitted
    above it are this module's docstring and `import pytest` itself.
    """
    tree = ast.parse(Path(__file__).read_text())
    body = list(tree.body)
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body.pop(0)

    assert isinstance(body[0], ast.Import)
    assert [a.name for a in body[0].names] == ["pytest"]

    call = body[1]
    assert isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)
    assert ast.unparse(call.value) == 'pytest.importorskip(\'playwright\')'


# --------------------------------------------------------------------------
# Integration seam — the tool against a throwaway static server
# --------------------------------------------------------------------------


def test_check_reaches_a_served_origin_and_accepts_a_good_page(served, tmp_path: Path) -> None:
    write, origin = served
    write(page_html())
    assert rc.check(origin, tmp_path / "shots") == 0
    assert (tmp_path / "shots" / "phone-projects.png").is_file()


def test_check_fails_on_a_page_that_is_missing_its_must_see_string(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point of Phase 0. A checker nobody has seen fail is not one."""
    write, origin = served
    write(page_html(break_page="projects"))
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert "projects is missing" in out
    assert "flock is missing" not in out


def test_check_still_runs_against_a_prototype_file(tmp_path: Path) -> None:
    proto = tmp_path / "shepherd-dark.html"
    proto.write_text(page_html())
    assert rc.check(str(proto), tmp_path / "shots") == 0


def test_fail_on_empty_is_the_arrival_check(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An origin that answers with nothing is named as such, and only when asked.

    Without the flag an empty page still fails — on the six missing nav entries.
    That is a different sentence, and the difference is the point: the arrival
    check says *the server handed over nothing*, which is the failure a page-by-
    page report cannot distinguish from a page that simply has no nav.
    """
    write, origin = served
    write("<!doctype html><html><head><link rel='icon' href='data:,'></head><body></body></html>")

    assert rc.check(origin, tmp_path / "shots", fail_on_empty=True) == 1
    assert "arrived at an empty page" in capsys.readouterr().out

    assert rc.check(origin, tmp_path / "shots") == 1
    assert "arrived at an empty page" not in capsys.readouterr().out


# --------------------------------------------------------------------------
# The JS gate — driven only through a subprocess, never imported (A6)
# --------------------------------------------------------------------------


def test_the_js_gate_accepts_a_valid_module(tmp_path: Path) -> None:
    good = tmp_path / "good.js"
    good.write_text("export function hi(n) { return `hello ${n}`; }\n")
    done = subprocess.run([PYTHON, str(JS_SYNTAX_CHECK), str(good)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_js_gate_rejects_a_syntax_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.js"
    bad.write_text("export function hi( { return ;;; }\n")
    done = subprocess.run([PYTHON, str(JS_SYNTAX_CHECK), str(bad)], capture_output=True, text=True)
    assert done.returncode == 1
    assert "bad.js" in done.stdout
