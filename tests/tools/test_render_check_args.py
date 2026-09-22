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


def load_render_check(path: Path = RENDER_CHECK, name: str = "render_check") -> ModuleType:
    """The tool, loaded by path because `tools/` is on no import path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `dataclasses` resolves a field's
    # annotations through `sys.modules[cls.__module__]`, so a module built by
    # `module_from_spec` and never registered cannot define a dataclass at all.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # The other half of the recipe. Registering before execution is what
        # makes the dataclass work; unregistering on failure is what stops a
        # half-initialised module being handed to the next importer as though
        # it had loaded. T10.1 copies this loader, so it copies both halves.
        del sys.modules[spec.name]
        raise
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
    {onclick}
  }});
}});
{onload}
</script>
</body></html>
"""


def page_html(*, break_page: str | None = None, onload: str = "", onclick: str = "") -> str:
    """A shell that satisfies the checker, optionally with one page sabotaged.

    `break_page` removes that page's `must_see` string and nothing else, so a
    failure names one page and the other five stay green — which is what makes
    the failure evidence rather than noise.

    `onload` is JS appended to the module body, `onclick` is JS appended to the
    nav click handler. Both exist so a fixture can be **structurally perfect**
    and still misbehave *after* the checker's arrival read — which is the only
    way to drive the console and banner gates past the first 700 ms.
    """
    nav = "".join(
        f'<a class="nav-item" data-page="{name}" href="#">{name}</a>' for name, _ in rc.PAGES
    )
    views = ""
    for name, must_see in rc.PAGES:
        body = "deliberately missing" if name == break_page else must_see
        views += f'<section id="page-{name}" hidden><h1>{body}</h1></section>'
    return PAGE_TEMPLATE.format(nav=nav, views=views, onload=onload, onclick=onclick)


def nav_only_html() -> str:
    """A page whose nav is empty: the checker can open **no** page at all.

    The floor M4 adds is about this run — six `no nav entry` failures and a
    `0 failures` line would have been byte-identical to twelve green assertions.
    """
    return PAGE_TEMPLATE.format(nav="", views="", onload="", onclick="")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # noqa: D102 - silence the server
        return

    def handle_error(self, *args: object) -> None:
        """Chromium abandons in-flight requests when a page closes, and the
        default handler prints a `ConnectionResetError` traceback into the
        middle of the pytest progress line. It is the browser hanging up, not
        a failure, and a traceback in green output is a thing readers have to
        learn to ignore — which is how they learn to ignore the real ones.
        """
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

    # Keyed on the *token*, not on one exact spelling. An assertion written as
    # `source.count('"#drawer-open"') == 1` survives `page.locator('#drawer-open')`
    # — single quotes, which is this module's own house style — and survives
    # `f'[data-page="{target}"].nav-item'`, attribute-first. Both are the
    # spelling a builder editing this file reaches for naturally. So: delete the
    # two definition lines, then require the tokens to be *absent* from what is
    # left. Quote-agnostic, order-agnostic, fails closed.
    rest = [
        line
        for line in RENDER_CHECK.read_text().splitlines()
        if not line.startswith(("NAV_SELECTOR =", "DRAWER_SELECTOR ="))
    ]
    remainder = "\n".join(rest)
    assert "drawer-open" not in remainder
    assert "data-page=" not in remainder


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


# --------------------------------------------------------------------------
# The console and banner gates, driven *past* the arrival read
#
# Phase 0's original negative control removed a `must_see` string, which proves
# the DOM assertion bites. A control that exercises one of two gates certifies
# one of two gates: nothing drove the console gate past its 700 ms window, and
# the window is exactly where the six-page navigation loop lives. Variants C, D
# and E are structurally perfect pages that misbehave only after arrival, and
# variant A is the clean control that keeps them honest — a change that makes
# everything fail is not a gate.
# --------------------------------------------------------------------------

LATE_THROW = "setTimeout(() => { throw new Error('FIXTURE boom late'); }, 1500);"
CLICK_THROW = "if (want === 'settings') { throw new Error('FIXTURE boom on settings'); }"
CLICK_BANNER = (
    "if (want === 'settings') {"
    " const d = document.createElement('div');"
    " d.className = 'boom';"
    " d.textContent = 'FIXTURE render failed';"
    " document.body.appendChild(d); }"
)


def test_variant_a_a_clean_page_still_passes(served, tmp_path: Path) -> None:
    """The control. Without it, C/D/E prove only that the tool can fail."""
    write, origin = served
    write(page_html())
    assert rc.check(origin, tmp_path / "shots") == 0


def test_variant_c_an_error_thrown_after_the_arrival_read_fails(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """C — throws at t=1500 ms, i.e. during the navigation loop."""
    write, origin = served
    write(page_html(onload=LATE_THROW))
    assert rc.check(origin, tmp_path / "shots") == 1
    assert "FIXTURE boom late" in capsys.readouterr().out


def test_variant_d_an_error_thrown_on_a_nav_click_fails_and_names_the_page(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D — and the report names *settings*, the page that caused it.

    The count is asserted too: two viewports, one report each. A gate that
    re-reads a list it never drains reports the same error once per remaining
    page, which is noise dressed as thoroughness.
    """
    write, origin = served
    write(page_html(onclick=CLICK_THROW))
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert out.count("FIXTURE boom on settings") == 2, out
    assert "after opening settings" in out


def test_variant_e_a_boom_banner_painted_on_a_nav_click_fails(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E — a banner the page paints on itself, after arrival.

    Separate from C/D on purpose: re-reading `console` does not re-check
    `.boom`, and this fixture throws nothing at all.
    """
    write, origin = served
    write(page_html(onclick=CLICK_BANNER))
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert "error banner" in out
    assert out.count("FIXTURE render failed") == 2, out


# --------------------------------------------------------------------------
# The floor: a run that checked nothing is not a passing run
# --------------------------------------------------------------------------


def test_a_run_that_opened_no_page_fails_and_says_how_little_it_checked(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write, origin = served
    write(nav_only_html())
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert "0 pages checked" in out
    assert "no pages were checked" in out


def test_a_good_run_reports_what_it_checked(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Six pages at two viewports, each screenshotted. Counted, not assumed."""
    write, origin = served
    write(page_html())
    assert rc.check(origin, tmp_path / "shots") == 0
    out = capsys.readouterr().out
    assert "12 pages checked" in out
    assert "12 screenshots" in out


def test_the_shots_directory_is_not_created_by_a_run_that_never_shot(
    served, tmp_path: Path
) -> None:
    write, origin = served
    write(nav_only_html())
    shots = tmp_path / "shots"
    assert rc.check(origin, shots) == 1
    assert not shots.exists()


# --------------------------------------------------------------------------
# Argument handling — an empty value is not an absent one
# --------------------------------------------------------------------------


def test_an_empty_url_is_rejected_rather_than_retargeted() -> None:
    """`--url "$VAR"` with `VAR` unset must not silently check the prototype."""
    with pytest.raises(SystemExit):
        rc.parse_args(["--url", ""])
    with pytest.raises(SystemExit):
        rc.parse_args(["--file", ""])


def test_extra_positionals_are_rejected_rather_than_dropped() -> None:
    with pytest.raises(SystemExit):
        rc.parse_args(["--url", "http://x/", "out", "extra"])
    with pytest.raises(SystemExit):
        rc.parse_args(["page.html", "out", "extra"])


# --------------------------------------------------------------------------
# The JS gate with nothing to parse
# --------------------------------------------------------------------------


def test_the_js_gate_fails_when_given_no_files() -> None:
    """`0 file(s) · 0 failure(s)` and exit 0 is a gate that passed by not running.

    Written as a shell glob in five later phases; bash's non-matching-glob
    passthrough is the *shell's* mitigation, and it evaporates under `nullglob`,
    zsh, `find | xargs`, or any Python or Make caller.
    """
    done = subprocess.run([PYTHON, str(JS_SYNTAX_CHECK)], capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no files given" in done.stdout


# --------------------------------------------------------------------------
# Routing exclusivity — the defect this whole tool was created by
#
# `docs/design/ui-decisions.md` §U18: every "hidden" page was rendering
# underneath the visible one, because an author class rule beat the UA
# `[hidden]` rule. A loop that asserts the clicked root *is visible* and never
# asserts the other five are *not* cannot catch that — a page with no routing
# script at all scored twelve green assertions.
# --------------------------------------------------------------------------


def unrouted_html() -> str:
    """Six nav anchors that do nothing, six roots all rendered at once."""
    nav = "".join(
        f'<a class="nav-item" data-page="{name}" href="#">{name}</a>' for name, _ in rc.PAGES
    )
    views = "".join(f'<section id="page-{n}"><h1>{m}</h1></section>' for n, m in rc.PAGES)
    return PAGE_TEMPLATE.format(nav=nav, views=views, onload="", onclick="")


def drawerless_html() -> str:
    """A shell missing `#drawer-open` — a Phase 5 deliverable that can be absent."""
    return page_html().replace('<button id="drawer-open" type="button">menu</button>', "")


def test_a_page_whose_roots_are_all_visible_fails(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """U18, as a fixture. Presence is not exclusivity."""
    write, origin = served
    write(unrouted_html())
    assert rc.check(origin, tmp_path / "shots") == 1
    assert "visible at once" in capsys.readouterr().out


def test_a_missing_drawer_control_fails_instead_of_hanging(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing nav entry already fails cleanly; the drawer must match it.

    Clicking a locator that matches nothing raises `TimeoutError` after 30s,
    `check()` never returns, and every failure already accumulated — plus the
    summary line — is lost. The run must still end with a report.
    """
    write, origin = served
    write(drawerless_html())
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert "no drawer control" in out
    assert "pages checked" in out, "the summary line must survive the failure"


# --------------------------------------------------------------------------
# The JS gate parses with the engine the code actually runs in
#
# The previous parser was ES2017, so it reported FAIL on optional chaining,
# class fields, `??=`, numeric separators and `import.meta` — all of which
# chromium has shipped for years. A gate that fails browser-correct code has
# two outcomes and both are worse than no gate: the JS gets written down to
# ES2017 to appease a parser nobody chose, or the check quietly stops being run
# while six tasks claim a gate they did not pass.
# --------------------------------------------------------------------------

MODERN_JS = """\
export class Panel {
  #count = 0;
  limit = 1_000;
  bump(o) {
    const n = o?.value ?? 0;
    this.#count ||= n;
    try { risky(); } catch { /* optional binding */ }
    return `${import.meta.url}:${this.#count}`;
  }
}
"""


def test_the_js_gate_accepts_syntax_that_chromium_accepts(tmp_path: Path) -> None:
    """Eight idioms an ES2017 parser rejects and every shipping browser accepts."""
    modern = tmp_path / "modern.js"
    modern.write_text(MODERN_JS)
    done = subprocess.run(
        [PYTHON, str(JS_SYNTAX_CHECK), str(modern)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_js_gate_is_a_parse_gate_not_an_execution_gate(tmp_path: Path) -> None:
    """A module that parses and then throws on a blank page is not a syntax error.

    Every page module wires the DOM at import time, so executing one outside
    its page throws — and counting that as a parse failure would make the gate
    unusable on exactly the files it exists for.
    """
    runtime = tmp_path / "runtime.js"
    runtime.write_text("document.querySelector('#nope').addEventListener('click', () => {});\n")
    done = subprocess.run(
        [PYTHON, str(JS_SYNTAX_CHECK), str(runtime)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_js_gate_tells_a_missing_file_apart_from_a_syntax_error(tmp_path: Path) -> None:
    """Two different defects must not wear one sentence."""
    missing = tmp_path / "not-here.js"
    done = subprocess.run(
        [PYTHON, str(JS_SYNTAX_CHECK), str(missing)], capture_output=True, text=True
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "not-here.js" in done.stdout
    assert "No such file" in done.stdout


def test_a_module_that_fails_to_load_is_not_left_registered(tmp_path: Path) -> None:
    """Registering before `exec_module` is half the recipe; this is the other.

    If execution raises, a half-initialised module stays in `sys.modules` and
    the next importer is handed it instead of an error. T10.1 copies this
    loader, so it must copy both halves. The fixture raises a plain exception
    and touches nothing outside the interpreter.
    """
    broken = tmp_path / "broken_probe.py"
    broken.write_text("raise ValueError('probe: this module does not load')\n")

    with pytest.raises(ValueError):
        load_render_check(broken, name="broken_probe")

    assert "broken_probe" not in sys.modules


def test_a_second_root_revealed_by_a_click_fails_after_that_click(
    served, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exclusivity is checked after every open, not only on arrival.

    This page arrives clean — nothing is open — and the routing works. It just
    also un-hides a root it was not asked for. Only the per-click check can see
    that, and the message it emits names the page that was clicked, which is
    how the report distinguishes the two branches.
    """
    write, origin = served
    write(page_html(onclick="document.getElementById('page-kanban').hidden = false;"))
    assert rc.check(origin, tmp_path / "shots") == 1
    out = capsys.readouterr().out
    assert "2 page roots visible at once" in out
    assert "on arrival:" not in out
