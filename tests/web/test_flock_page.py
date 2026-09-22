"""The Flock page (U7–U11, U16, U1) — three panes, the legend, the cards.

There is no browser and no JS runtime on this host (D51, K8), so the rendering
half of this module is a scan of the bytes the server actually serves, exactly
as `test_palette.py`'s and `test_frontend_escaping.py`'s are. What that proves
and what it does not is stated plainly: it proves the *shipped source* carries
the branch, the table and the wording; it does not prove a pixel. The pixels are
Phase 10's live check and the human look there.

The **payload** half — E21's unassigned project, the keys the page reads —
runs over HTTP against a real store through `web/conftest.py::Client`, which is
the same seam every other module in `tests/web/` uses. The two halves are
labelled per test, because a scan that is read as a payload proof is how a page
comes to read a key the server never emits.
"""

from __future__ import annotations

import re
from pathlib import Path

from web.conftest import NOW, Client, seed
from web.test_session_page import code_only

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import SessionState
from shepherd.core.stops import PALETTE
from shepherd.store.db import Store
from shepherd.store.models import UNASSIGNED_PROJECT_ID

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"

#: `const BUCKET_ACTS = { … }` — U10's `acts:` line, read out of the source.
_JS_TABLE = re.compile(r"const\s+BUCKET_(ACTS|LABEL|MARK)\s*=\s*\{(.*?)\n\}", re.DOTALL)
_JS_ENTRY = re.compile(r"(\w+):\s*\"([^\"]+)\"")

#: `:root { … --b: var(--unclassified) }` — the fallback a class-less card takes.
_ROOT_B = re.compile(r"--b:\s*var\(--([a-z_]+)\)")


def flock_code() -> str:
    """The module with its comments removed.

    Every **absence** below is asserted against this rather than the raw text:
    this file's own header names `innerHTML`, `.sort(` and "needs attention" in
    prose, explaining why none of them may appear, and a scan that cannot tell a
    comment from a statement fails on the explanation instead of on the code.
    """
    return code_only(flock_js())


def flock_js() -> str:
    """The shipped module, or `""` when it is not shipped at all.

    A missing file is a *finding*, not a collection error: the assertion in
    `test_the_flock_page_ships_its_module` names what is absent rather than the
    harness raising on the open, which is the difference between a red and a
    broken run.
    """
    path = STATIC_ROOT / "flock.js"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def css() -> str:
    return (STATIC_ROOT / "app.css").read_text(encoding="utf-8")


def js_table(which: str) -> dict[str, str]:
    for kind, body in _JS_TABLE.findall(flock_js()):
        if kind == which:
            return dict(_JS_ENTRY.findall(body))
    return {}


def function_body(source: str, name: str) -> str:
    """The text of one top-level function, up to the next one."""
    start = source.index(f"function {name}(")
    rest = source[start + 1 :]
    end = rest.find("\nfunction ")
    tail = rest.find("\nexport function ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


# ----- the module itself ------------------------------------------------------


def test_the_flock_page_ships_its_module() -> None:
    """U9's page is a module the server serves, with the names it exports."""
    source = flock_js()
    assert source != "", "src/shepherd/web/static/flock.js is not shipped"
    for name in (
        "export function mountFlock(",
        "export function renderFlock(",
        "export const BUCKET_LABEL",
        "export const BUCKET_MARK",
    ):
        assert name in source, name


# ----- U8 / E19: relative time -------------------------------------------------


def test_a_session_with_no_timestamp_reads_never_seen() -> None:
    """E19 / U8. **Scan half.** A datum we do not have is not rounded *newer*.

    The whole point of the branch is the direction of the lie it prevents:
    `just now` for a session nobody has ever seen tick claims the freshest
    possible reading of a field that is absent. `never seen` is the honest one,
    and it is a named constant so the wording cannot drift into a blank.
    """
    source = flock_js()
    assert re.search(r'NEVER_SEEN\s*=\s*"never seen"', source), "the constant is named"

    body = function_body(source, "ago")
    # Three absences, one answer. A branch that handled only `null` would let an
    # undefined field fall through to `Date.parse(undefined)` -> NaN.
    assert "timestamp === null" in body
    assert "timestamp === undefined" in body
    assert 'timestamp === ""' in body
    # …and an unparseable timestamp is also a timestamp we do not have.
    assert "Number.isNaN(then)" in body
    assert body.count("NEVER_SEEN") == 2, body

    # The control, which says which branch of two this certifies: `just now` is
    # reachable, so the test above is not passing because nothing ever says it.
    assert '"just now"' in body


def test_relative_time_is_spelled_out_and_scales_to_years() -> None:
    """U8. **Scale half.** `2 minutes ago`, `11 days ago`, `1 year ago`.

    The six units are asserted as a whole rather than sampled: a scale missing
    `week` does not fail on a week-old session, it silently reports `7 days ago`,
    which is not wrong enough to notice and not what U8 asked for.
    """
    source = flock_js()
    scale = re.search(r"const SCALE = \[(.*?)\n\];", source, re.DOTALL)
    assert scale is not None, "the scale is a named table"
    units = re.findall(r'\[(\d+), "(\w+)"\]', scale.group(1))
    assert units == [
        ("31536000", "year"),
        ("2592000", "month"),
        ("604800", "week"),
        ("86400", "day"),
        ("3600", "hour"),
        ("60", "minute"),
    ], units
    # Plural is computed, not baked: `1 year ago`, `2 years ago`.
    assert 'count === 1 ? "" : "s"' in function_body(source, "ago")


# ----- U7: the card carries four things and no more ---------------------------


def test_the_card_carries_four_things_and_no_more() -> None:
    """U7. **Scan half.** Glyph and colour, title, the ask, relative time.

    Deliberately out: model, ownership, session id, confidence, workspace path —
    all real, none of them changes which card you tap. The exclusions are
    asserted by name, because "four things" is only checkable if the fifth is
    named; a card that quietly grew a `card-model` span would otherwise pass.
    """
    body = function_body(flock_js(), "sessionCard")
    for present in ("card-mark", "card-title", "card-ask", "card-age"):
        assert present in body, present
    code = code_only(body)
    for absent in ("card-model", "card-ownership", "card-cwd", "card-confidence", "meta-part"):
        assert absent not in code, absent
    # D21's list is not on the card. It renders in the session pane's header,
    # which is where §12 already placed it (D67).
    assert "next_actions" not in code
    assert "actionButton" not in code


def test_the_ask_is_verbatim_and_only_when_there_is_one() -> None:
    """U7. **Scan half.** The actual ask — never "session needs attention".

    Two sources, in order: a waiting session carries `needs_you_reason` and a
    stopped one carries the classifier's `why`. Neither is a sentence this page
    composed, and a session with neither gets no line rather than a placeholder.
    """
    body = function_body(flock_js(), "askOf")
    assert "needs_you_reason" in body
    assert "session.why" in body
    assert "return null" in body
    assert "needs attention" not in flock_code()


def test_progress_is_a_hairline_never_a_text_line() -> None:
    """U7. **Scan half.** `2/5 tasks` was a fifth item on a four-item card."""
    source = flock_js()
    body = function_body(source, "progressBar")
    assert "card-bar" in body
    # No *prose*: the bar reads `tasks_done`/`tasks_total` and writes a width.
    # The old page's text line, by its old name and by its old shape, so the
    # port cannot bring it back under either.
    assert "progressOf" not in code_only(source)
    assert "tasks`" not in code_only(source)
    assert '" tasks"' not in code_only(source)
    assert "card-bar" in body


def test_every_card_carries_one_of_the_eight_bucket_classes() -> None:
    """U16 / principle 5. A card that forgets its class is a *plausible* lie.

    `--b` falls back to the unclassified grey at `:root`, so an unclassed card
    does not render broken — it renders as a believable `unknown` session. That
    is why the class is asserted at the construction site and why the fallback
    is asserted here too: the second half is what makes the first half matter.
    """
    body = function_body(flock_js(), "sessionCard")
    assert "`card bucket-${bucket}`" in body
    assert "bucketOf(session)" in body

    fallback = _ROOT_B.search(css())
    assert fallback is not None, "`--b` has a documented fallback"
    assert fallback.group(1) == "unclassified", fallback.group(1)


# ----- U10 / U1: the legend and its sheet --------------------------------------


def test_the_legend_acts_line_comes_from_palette_who_acts() -> None:
    """U10. The field that already exists and actually distinguishes the buckets.

    Compared to `PALETTE` rather than trusted, for the same reason the label and
    glyph tables are: a hand-copied string is how a palette drifts.
    """
    acts = js_table("ACTS")
    assert set(acts) == {bucket.value for bucket in PALETTE}
    for bucket, style in PALETTE.items():
        assert acts[bucket.value] == style.who_acts, bucket
    assert "acts: " in flock_js()


def test_the_legend_sheet_explains_all_eight_at_once() -> None:
    """U1. One `ⓘ` opens a sheet; a tap on a key opens the same sheet.

    A key that did nothing on tap would be a dead control, and eight
    explanations read better together than one at a time on a phone.
    """
    source = flock_js()
    sheet = function_body(source, "openLegendSheet")
    assert "dlg-legend-list" in sheet
    assert "dlg-legend" in sheet
    assert "showModal()" in sheet

    legend = function_body(source, "renderLegend")
    # Both routes into the sheet, and the pointer-only popover beside them.
    assert 'key.addEventListener("click", openLegendSheet)' in legend
    assert 'info.addEventListener("click", openLegendSheet)' in legend
    assert "mouseenter" in legend and "focus" in legend


def test_the_legend_and_sheet_read_the_blurb_table_they_declare() -> None:
    """The one table on this page nothing server-side can check, said out loud.

    `BucketStyle` carries a colour, a glyph, a label and `who_acts` — nothing
    longer — so the sheet's prose has no counterpart to be compared against. It
    is asserted to be **total over the eight buckets** instead, because the
    failure mode that is checkable is a sheet row that renders `undefined`.
    """
    source = flock_js()
    blurb = re.search(r"const BUCKET_BLURB = \{(.*?)\n\};", source, re.DOTALL)
    assert blurb is not None
    named = set(re.findall(r"^  (\w+):", blurb.group(1), re.MULTILINE))
    assert named == {bucket.value for bucket in PALETTE}, named
    assert "BUCKET_BLURB[bucket]" in function_body(source, "openLegendSheet")


# ----- §13: the two ported sinks ----------------------------------------------


def test_the_two_icons_are_built_as_nodes_not_as_markup() -> None:
    """F6. The prototype assigned both through `innerHTML`; both are findings.

    `renderLegend`'s `ⓘ` (prototype line 2520) and `BACK_BUTTON`'s chevron
    (2858) concatenated SVG into a sink, and §13 permits a sink only when its
    right-hand side is a single quoted literal with no concatenation. Neither
    was one. `createElementNS` is required rather than `createElement`: an
    `<svg>` built in the HTML namespace renders as nothing at all, so the
    namespace is the assertion rather than the element name.
    """
    source = flock_js()
    code = flock_code()
    assert "innerHTML" not in code
    assert "outerHTML" not in code
    assert "insertAdjacentHTML" not in code
    assert 'SVG_NS = "http://www.w3.org/2000/svg"' in source
    assert source.count("createElementNS(SVG_NS") == 2

    # …and both icons really go through it, rather than one being live markup.
    assert "infoIcon()" in function_body(source, "renderLegend")
    assert "chevronIcon()" in function_body(source, "backButton")


# ----- B3 / principle 5: the stop-summary strip -------------------------------


def test_the_stop_summary_strip_is_filled_by_the_flock_page() -> None:
    """B3. The strip stayed when the rail went (D66).

    Three numbers, three meanings, none folded into another. Principle 5's
    headline metric is the unknown rate, and a page that hid it would be hiding
    the one number that says how much of the rest of the page is a guess.
    """
    body = function_body(flock_js(), "renderStopSummary")
    for slot in ("unknown-rate", "low-confidence", "unclassified"):
        assert slot in body, slot
    for field in ("unknown_rate", "completed_low_confidence", "unclassified"):
        assert field in body, field
    # A missing number reads `unknown`, not `0` — a zero is a claim.
    assert "UNKNOWN" in body


# ----- §16: the server orders ---------------------------------------------------


def test_the_flock_page_does_not_re_derive_the_order() -> None:
    """§16. `fleet_tree` orders by `fleet_bucket_sort_key`; the page renders it.

    The four banned shapes are named rather than described, because a page that
    "does not sort" is not checkable and a page with no `.sort(` in it is.
    """
    code = flock_code()
    for shape in (".sort(", "localeCompare", "BUCKET_ORDER", "FLEET_STATE_ORDER", "fleetSortKey"):
        assert shape not in code, shape


# ----- U9: three panes, and the drill-down ------------------------------------


def test_the_flock_is_three_panes_with_a_back_chevron() -> None:
    """U9. projects → session cards → the session, one level at a time on a phone.

    The level is a data attribute on the page root and `app.css` decides which
    columns show, so a wide screen keeps all three and nothing here measures a
    viewport — the media query is the one place that knows about screen width.
    """
    source = flock_js()
    for host in ("flock-projects", "flock-cards", "flock-sessions-head"):
        assert host in source, host
    assert "export function showLevel(" in source
    assert 'page.dataset.level = button.dataset.level' in function_body(source, "mountFlock")
    assert 'querySelectorAll(".back[data-level]")' in flock_js()

    # …and the stylesheet really keys the columns off that attribute, so the
    # attribute is not a value nothing reads.
    rules = css()
    for level, column in (
        ("projects", "col-projects"),
        ("sessions", "col-sessions"),
        ("detail", "col-detail"),
    ):
        pattern = rf'\.herd\[data-level="{level}"\]\s+\.{column}\b'
        assert re.search(pattern, rules) is not None, level


# ----- the payload half: what the server actually emits -----------------------


def test_the_flock_page_reads_the_keys_the_tree_emits(client: Client, store: Store) -> None:
    """**Payload half**, over HTTP. The projects pane keys off `project_id`.

    D22: a project *is* a workspace, and the consumer-facing key is `project_id`
    — `fleet_tree`'s workspace entries carry it while the session rows inside
    carry `workspace_id`. A page that read `workspace_id` off the workspace
    would render a list of `undefined` projects and select none of them, which
    is precisely the class of bug a scan cannot see.
    """
    session = seed(store)
    store.apply_fold_delta(session.id, FoldDelta(state=SessionState.RUNNING, last_event_at=NOW))
    data = client.request("/api/fleet/tree").json()["data"]
    assert isinstance(data, dict)
    workspaces = data["workspaces"]
    assert isinstance(workspaces, list)
    workspace = workspaces[0]
    assert set(workspace) == {"project_id", "name", "sessions"}, sorted(workspace)

    source = flock_js()
    assert "workspace.project_id" in source
    assert "workspace.workspace_id" not in source
    # Every field the card reads is a field the row really carries.
    row = workspace["sessions"][0]
    for field in ("session_id", "title", "bucket", "last_event_at", "needs_you_reason",
                  "why", "tasks_done", "tasks_total"):
        assert field in row, field


def test_unassigned_sessions_render_on_the_flock_page(client: Client, store: Store) -> None:
    """E21 / N1 / D59. **Payload half.** `Unassigned` is a project, not a gap.

    Migration 004 seeds the reserved project and a session that matched no
    declared project lands in it. The Flock's first pane is the tree's
    workspaces, so the honest question is whether the reserved one arrives there
    — a page that filtered it out would lose every unclaimed session silently.
    """
    session = store.register_session(
        engine_session_id="eng-unassigned",
        workspace_id=UNASSIGNED_PROJECT_ID,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=__import__("shepherd.core.states", fromlist=["Origin"]).Origin.EXTERNAL,
        ownership=__import__("shepherd.core.states", fromlist=["Ownership"]).Ownership.ATTACHED,
    )
    store.apply_fold_delta(session.id, FoldDelta(state=SessionState.RUNNING, last_event_at=NOW))

    data = client.request("/api/fleet/tree").json()["data"]
    assert isinstance(data, dict)
    workspaces = data["workspaces"]
    assert isinstance(workspaces, list)
    reserved = [space for space in workspaces if space["project_id"] == UNASSIGNED_PROJECT_ID]
    assert len(reserved) == 1, workspaces
    assert reserved[0]["name"] == "Unassigned"
    assert [row["session_id"] for row in reserved[0]["sessions"]] == [session.id]

    # The page renders whatever workspaces it was handed, with no exclusion:
    # the loop is over `view.workspaces` and nothing filters it.
    source = flock_js()
    assert "for (const workspace of view.workspaces)" in source
    assert "Unassigned" not in flock_code(), "the page never special-cases it"


def test_the_page_never_mints_a_seventh_page_root() -> None:
    """`PAGE_ROOT_SELECTOR` is `[id^="page-"]`, so the prefix is a namespace.

    `tools/render_check.py` counts visible page roots by that selector and fails
    a width on "N page roots visible at once". Any element this page *creates*
    with an id beginning `page-` therefore becomes a seventh root — and a
    permanently-visible one, like the prototype's `id="page-title"` heading,
    reports as a routing failure on every page at both widths, with a message
    about routing that is not about routing.

    The shipped shell owns the six roots and nothing else may claim one, so this
    module reads `#page-flock` and never writes a `page-` id. The assertion is
    on **assignment and creation**, not on the string: reading the root by name
    is exactly what the page is supposed to do.
    """
    for name in ("flock.js", "session.js"):
        body = code_only((STATIC_ROOT / name).read_text(encoding="utf-8"))
        for shape in ('.id = "page-', ".id = `page-", 'setAttribute("id", "page-'):
            assert shape not in body, f"{name}: {shape}"
        # Arrival: the scan read a file that really does name the root, so it is
        # not passing because it opened something with no ids in it at all.
    assert 'getElementById("page-flock")' in (STATIC_ROOT / "flock.js").read_text(
        encoding="utf-8"
    )
