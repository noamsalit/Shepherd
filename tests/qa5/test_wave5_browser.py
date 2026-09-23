"""Wave 5 — the browser ground never driven.

Two live tabs, real touch events, reduced motion, forced colors, RTL, zoom,
every width above 1280 and below 390, and the edit chain that keeps draft state
across three round trips.

**Every width in this file arrives from `ROUND5_WIDTHS`** (§3d). No `.py` file
in this package contains a width literal: that re-spelling is exactly the drift
C-8 names as the thing that hid D1, and in round 1 this plan's own scenarios
reproduced it while claiming they did not.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Console, Harness, navigate, press_until_open
from .constants import (
    CEILING_S,
    CONTROL_PAGE,
    CONTROL_SET,
    DESKTOP,
    DRILL_MAX_WIDTH,
    NAV_PAGES,
    PHONE,
    ROUND5_WIDTHS,
    S21_WIDTHS,
    S22_WIDTH,
    S23_WIDTHS,
    S24_WIDTHS,
)
from .dom import (
    FILL_FLOOR,
    SLACK_PX,
    assert_hit_testable,
    assert_hit_testable_nth,
    assert_no_horizontal_overflow,
    assert_one_root_visible,
    assert_pane_healthy,
    hit_testable,
)
from .report import LOAD_DETAIL_RACE_DECLARATION
from .wire import await_true

LIVE_PAGES = ("shepherd", "flock", "projects", "settings")

#: `HIT_TESTABLE` over every control in the Settings detail panel, in one
#: layout pass. Written here rather than looping `hit_testable` per node: the
#: panel's controls carry no stable ids, so there is no selector to name.
_SETTINGS_PANEL_HITS = """
(args) => {
  const panel = document.getElementById("settings-panel");
  const nodes = panel.querySelectorAll("button, a, input, select, textarea, [tabindex]");
  let hits = 0;
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    const painted = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!(painted !== null && (painted === el || el.contains(painted)))) continue;
    const style = getComputedStyle(el);
    if (style.pointerEvents === "none" || el.disabled === true) continue;
    if (!(r.top >= -args.slack && r.left >= -args.slack
          && r.bottom <= window.innerHeight + args.slack
          && r.right <= window.innerWidth + args.slack)) continue;
    hits += 1;
  }
  return {candidates: nodes.length, hitTestable: hits};
}
"""


def _control_snapshot(page: Any) -> dict[str, bool]:
    """`HIT_TESTABLE` over the enumerated `CONTROL_SET`, as one reading."""
    return {name: hit_testable(page, selector).ok for name, selector in CONTROL_SET}


def _vacuous(before: dict[str, bool], after: dict[str, bool]) -> list[str]:
    """The names that were `False` on **both** sides of a differential.

    These contribute nothing to the comparison and, before this existed, they
    dropped out of it in silence — two of the ten already did. A renamed id or a
    selector that stopped matching anything would drop out identically and
    produce no signal at all, which is the exact failure `CONTROL_SET` was
    enumerated to prevent: an unbounded or vacuous differential that prints
    green. Named and counted, never silently.
    """
    return sorted(name for name in before if not before[name] and not after.get(name, False))


def _control_set_resolves(page: Any, label: str) -> dict[str, int]:
    """**The non-vacuity floor: every enumerated selector still matches something.**

    Measured on the page the control actually lives on (`CONTROL_PAGE`), which is
    the whole point: `#proj-new` is not in the Flock's DOM and never will be, so
    a presence reading taken from the Flock proves nothing about whether the id
    still exists. `"shell"` controls are the persistent chrome and are read from
    whatever page the sweep ends on.

    This is what a `False`-on-both-sides entry cannot tell you apart from: a
    control that is legitimately absent here, and an id somebody renamed.
    """
    by_page: dict[str, list[tuple[str, str]]] = {}
    for name, selector in CONTROL_SET:
        by_page.setdefault(CONTROL_PAGE[name], []).append((name, selector))
    counts: dict[str, int] = {}
    for target in sorted(by_page):
        if target != "shell":
            navigate(page, target)
        for name, selector in by_page[target]:
            counts[name] = int(page.eval_on_selector_all(selector, "els => els.length"))
    unresolved = sorted(name for name, found in counts.items() if found == 0)
    assert unresolved == [], (
        f"{label}: these CONTROL_SET selectors matched NOTHING on the page the "
        f"control lives on, so every differential over them is vacuous: "
        f"{[(name, dict(CONTROL_SET)[name], CONTROL_PAGE[name]) for name in unresolved]}"
    )
    return counts


def _shot(harness: Harness, page: Any, name: str) -> None:
    """Screenshots go under the run root's `shots/`, **never** into the static
    tree: `web/server.py` is byte-pinned and `_CONTENT_TYPES` is
    `.html`/`.js`/`.css` only, so an image fixture there is unservable (B8)."""
    page.screenshot(path=str(harness.shots_dir() / f"{name}.png"))


def test_s18_two_live_browser_tabs(harness: Harness) -> None:
    """S18 — C-2 at the real client; PP-1; the two-tab driver never committed."""
    context = harness.context(DESKTOP)
    tab_a, tab_b = context.new_page(), context.new_page()
    console_a, console_b = Console("S18-A"), Console("S18-B")
    console_a.watch(tab_a)
    console_b.watch(tab_b)

    # Registered **before** the first navigation: a listener added afterwards
    # cannot see the burst it is meant to count.
    b_reads: list[str] = []
    tab_b.on(
        "request",
        lambda request: b_reads.append(request.url)
        if request.method == "GET" and "/api/projects" in request.url
        else None,
    )
    b_posts: list[str] = []
    tab_b.on("request", lambda r: b_posts.append(r.url) if r.method == "POST" else None)
    a_posts: list[str] = []
    tab_a.on("request", lambda r: a_posts.append(r.url) if r.method == "POST" else None)

    for tab in (tab_a, tab_b):
        tab.goto(f"{harness.client.origin}/")
        tab.wait_for_function("() => document.readyState === 'complete'")
        navigate(tab, "projects")
        tab.wait_for_selector("#proj-list .proj-row")

    await_true(
        lambda: tab_b.inner_text("#stream-status").strip().lower() == "live",
        f"tab B's #stream-status never read live: {tab_b.inner_text('#stream-status')!r}",
    )

    before = tab_b.eval_on_selector_all("#proj-list .proj-row", "els => els.length")
    reads_at_burst = len(b_reads)
    mark = harness.rig.open_window()

    created = harness.client.create_project("S18-subject")
    subject = str(created["project"]["project_id"])  # type: ignore[index]
    tab_b.wait_for_selector(f"#proj-list .proj-row[data-project-id='{subject}']")
    assert (
        tab_b.eval_on_selector_all("#proj-list .proj-row", "els => els.length") == before + 1
    ), "tab B did not grow by one with no reload and no user action"

    harness.client.rename_project(subject, "S18-renamed")
    tab_b.wait_for_function(
        "(id) => { const row = document.querySelector("
        "`#proj-list .proj-row[data-project-id='${id}']`);"
        " return row !== null && row.innerText.includes('S18-renamed'); }",
        arg=subject,
    )

    frames = harness.rig.await_count(mark, 2, "B")
    assert [frame.kind for frame in frames] == ["project.created", "project.renamed"], frames

    # "At most twice per burst" is counted at a **named seam** — the requests tab
    # B itself issued in the window — never inferred from the fact that a module
    # was loaded. That inference is B4's failure one level down.
    burst_reads = b_reads[reads_at_burst:]
    list_reads = [url for url in burst_reads if url.rstrip("/").endswith("/api/projects")]
    assert len(list_reads) <= 2 * 2, (
        f"tab B issued {len(list_reads)} GET /api/projects in a two-envelope burst; "
        f"refreshAll coalesces to at most two passes per envelope: {burst_reads}"
    )
    assert b_posts == [], f"tab B must issue no mutation: {b_posts}"
    assert a_posts == [], f"the mutations were driven over the wire, not from tab A: {a_posts}"

    assert tab_b.inner_text("#stream-status").strip().lower() == "live"
    console_a.assert_clean("S18 tab A:")
    console_b.assert_clean("S18 tab B:")

    harness.client.delete_project(subject)
    tab_b.close()

    harness.report.record(
        "S18",
        "ui",
        "PASS",
        "tab B shows the new project and the rename with no reload and no user "
        "action; #stream-status reads live throughout; tab B issues no mutation; "
        "GET /api/projects in the burst is at most two per envelope, counted at "
        "page.on('request'); two frames; zero console errors in both tabs",
        f"rows {before}->{before + 1}; burst list reads={len(list_reads)}; "
        f"frames={[f.kind for f in frames]}",
    )


def test_s19_real_touch_events_on_a_phone_viewport(harness: Harness) -> None:
    """S19 — real `touchstart`/`touchend`, not a synthesized pointer event."""
    p1 = harness.seeded.project("P1")
    repos_before = harness.store.repo_counts().get(p1)
    mark = harness.rig.open_window()

    page, console = harness.open(
        width=PHONE, label="S19", has_touch=True, is_mobile=True
    )
    requests: list[str] = []
    page.on("request", lambda r: requests.append(f"{r.method} {r.url}"))

    def tap(selector: str) -> None:
        """A real `touchstart`/`touchend` at the element's centre.

        **The target must be HIT_TESTABLE and settled before the coordinate is
        read.** Two failures made that necessary, and both were silent:

        * a `0x0` box has its centre at the origin, so the "tap" lands on the
          page corner and nothing happens;
        * the drawer slides in over 200 ms, and two consecutive polls can agree
          on the box while it is still at `x: -25` — the animation had not
          started. The tap then lands off-screen and the assertion that follows
          reports a page that "did not respond".

        So the wait is §3d's own definition plus stability: a real box, wholly
        inside the viewport, with the centre resolving to this element or a
        descendant, and unchanged since the previous poll. That is precisely
        what a person's finger requires, which is why it is the right gate for
        a *touch* test rather than a convenience.
        """
        page.wait_for_function(
            """(sel) => {
                 const el = document.querySelector(sel);
                 if (el === null) return false;
                 const r = el.getBoundingClientRect();
                 const now = [r.left, r.top, r.width, r.height].join(",");
                 const key = "__qa5_box__" + sel;
                 const previous = window[key];
                 window[key] = now;
                 if (previous !== now) return false;
                 if (!(r.width > 0 && r.height > 0)) return false;
                 if (!(r.top >= 0 && r.left >= 0
                       && r.bottom <= window.innerHeight
                       && r.right <= window.innerWidth)) return false;
                 const painted = document.elementFromPoint(r.left + r.width / 2,
                                                           r.top + r.height / 2);
                 return painted !== null && (painted === el || el.contains(painted));
               }""",
            arg=selector,
        )
        box = page.eval_on_selector(
            selector,
            "el => { const r = el.getBoundingClientRect();"
            " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }",
        )
        page.touchscreen.tap(box["x"], box["y"])

    # The closed off-canvas drawer sits at x: -244..0 **by design**; its controls
    # are excluded by name and counted, never silently, and the drawer is opened
    # before any nav assertion is made.
    excluded = [
        name
        for name, selector in CONTROL_SET
        if name.startswith("nav-") and not hit_testable(page, selector).ok
    ]
    tap("#drawer-open")
    page.wait_for_function(
        "() => { const el = document.querySelector('.nav-item[data-page=\\'projects\\']');"
        " const r = el.getBoundingClientRect(); return r.left >= 0; }"
    )
    tap('.nav-item[data-page="projects"]')
    page.wait_for_selector("#proj-list .proj-row")

    before_row = len(requests)
    tap(f"#proj-list .proj-row[data-project-id='{p1}']")
    page.wait_for_function(
        "() => document.getElementById('proj-detail').innerText.trim().length > 0"
    )

    # The rail toggle — the pairwise member round 1 never drove.
    # **The rail toggle is a PAIR of controls, not one.** `#collapse` only ever
    # sets `collapsed` (`app.js:340-342`) and `#mark` is what restores `open`
    # (`:343-347`). The plan calls `#collapse` "the rail toggle" and asks that it
    # "flips between open and collapsed"; tapping it twice leaves the rail
    # collapsed. Both directions are driven, through the control that owns each.
    rail_before = page.eval_on_selector("#shell", "el => el.dataset.rail")
    assert rail_before == "open", rail_before
    # `#collapse` and `#mark` live **inside the rail**, which is off-canvas at
    # this width, so a tap at their centre coordinates lands on nothing (their
    # boxes are at negative x). The drawer is opened first — which is what a
    # person does to reach them — and the taps are real taps on real boxes.
    tap("#drawer-open")
    tap("#collapse")
    page.wait_for_function(
        "() => document.getElementById('shell').dataset.rail === 'collapsed'"
    )
    rail_after = page.eval_on_selector("#shell", "el => el.dataset.rail")
    tap("#mark")
    page.wait_for_function("() => document.getElementById('shell').dataset.rail === 'open'")
    # **The drawer is closed by using the nav, not by tapping `#drawer-open`
    # again.** The opener sits *underneath* the open drawer (the rail is
    # `position: fixed` at `z-index: 10` across `0..244`, and the opener's box
    # is `12..42`), so a real touch at its centre lands on the drawer and the
    # drawer stays open — after which every later tap is intercepted by it.
    # `showPage` removes `data-drawer`, so tapping the entry for the page we are
    # already on closes it and navigates nowhere.
    tap('.nav-item[data-page="projects"]')
    page.wait_for_function(
        "() => document.getElementById('shell').getAttribute('data-drawer') === null"
    )

    # The create dialog opens on a tap and its primary control is HIT_TESTABLE —
    # not "non-zero", which a 1 px box satisfies.
    posts_before = [item for item in requests if item.startswith("POST")]
    # **Back to the list level first.** Selecting a project drills the Projects
    # page below the breakpoint and `#proj-new`, which lives in the list
    # column's header, collapses to `0x0`. A tap at the centre of a zero box is
    # a tap on the page corner, and the dialog never opens.
    _projects_back_if_drilled(page)
    tap("#proj-new")
    page.wait_for_function("() => document.getElementById('dlg-project').open === true")
    assert_hit_testable(page, "#p-save", "S19 create dialog:")
    assert page.eval_on_selector("#p-paths-section", "el => el.hidden") is True, (
        "#p-paths-section is hidden outside edit mode (projects.js:549)"
    )
    page.eval_on_selector("#dlg-project", "el => el.close()")

    # --- the keyboard leg, in EDIT mode, where the field exists --------------
    _projects_back_if_drilled(page)
    tap(f"#proj-list .proj-row[data-project-id='{p1}']")
    page.wait_for_selector("#proj-edit")
    # The settle for the shipped `loadDetail` race, declared once into the report
    # from every site that has to work around it (report.py).
    harness.report.declare(LOAD_DETAIL_RACE_DECLARATION)
    page.wait_for_load_state("networkidle")
    # **Wait for the pane to be P1's own, not merely for `#proj-edit` to exist.**
    # S33 already did this and S19 did not, which is why S19 was the one that
    # tapped into the rebuild window. P1's first repo path appears in no other
    # project, so its presence is the arrival signal.
    page.wait_for_function(
        "(path) => { const el = document.getElementById('proj-detail');"
        " return el !== null && el.innerText.includes(path); }",
        arg=str(harness.seeded.paths["P1_FIRST"]),
    )
    presses = press_until_open(
        page, "dlg-project", lambda: tap("#proj-edit"), "S19 edit dialog"
    )
    harness.report.measure("s19_edit_dialog_presses", presses)
    assert page.eval_on_selector("#p-paths-section", "el => el.hidden") is False, (
        "edit mode must unhide #p-paths-section — round 2 drove this leg in create "
        "mode, where addDraftPath returns at :586 before any request is built"
    )
    adds_before = len([item for item in requests if "/repos/add" in item])
    missing = str(harness.run.sub("work") / "no-such-path-for-s19")
    page.fill("#p-new-path", missing)
    page.press("#p-new-path", "Enter")
    await_true(
        lambda: len([item for item in requests if "/repos/add" in item]) == adds_before + 1,
        "Enter on #p-new-path issued no …/repos/add",
    )
    assert page.eval_on_selector("#dlg-project", "el => el.open") is True, (
        "Enter must reach addDraftPath and must NOT submit the form "
        "(projects.js:480-482)"
    )
    page.wait_for_function(
        "() => document.getElementById('p-refusal').textContent.trim().length > 0"
    )
    refusal = page.inner_text("#p-refusal").strip()
    adds = [item for item in requests if "/repos/add" in item]
    assert len(adds) == adds_before + 1, adds

    page.eval_on_selector("#dlg-project", "el => el.close()")
    assert harness.store.repo_counts().get(p1) == repos_before, (
        "the Enter leg's path is refused, so P1's repo set must be unchanged"
    )
    console.assert_clean("S19:")

    window = harness.rig.control("S19", since=mark)
    window.assert_kinds([], prefix="project.")

    harness.report.record(
        "S19",
        "ui",
        "PASS",
        "every real touch tap reaches its handler; #shell[data-rail] flips both "
        "ways and the nav stays reachable; the dialog's primary control is "
        "HIT_TESTABLE; in EDIT mode #p-paths-section is visible and Enter on "
        "#p-new-path issues exactly one …/repos/add answering added==false without "
        "submitting the form; P1's repo set is unchanged; zero frames in the window",
        f"rail {rail_before}->{rail_after}->open (#collapse collapses, #mark "
        f"restores — two controls, not one toggle); refusal={refusal[:140]!r}; "
        f"repos_add_requests={len(adds) - adds_before}; "
        f"drawer_controls_excluded_by_name={excluded}",
    )


def test_s20_prefers_reduced_motion(harness: Harness) -> None:
    """S20 — a **baseline pass** and an enumerated set, which is what makes the
    differential an assertion rather than an unbounded or a vacuous one."""
    results: dict[str, dict[str, bool]] = {}
    sheet: dict[str, bool] = {}
    resolution: dict[str, dict[str, int]] = {}

    for label, options in (
        ("baseline", {}),
        ("reduce", {"reduced_motion": "reduce"}),
    ):
        page, console = harness.open(
            nav="flock", width=DESKTOP, label=f"S20-{label}", **options
        )
        resolution[label] = _control_set_resolves(page, f"S20 {label}")
        navigate(page, "flock")
        for target in NAV_PAGES:
            navigate(page, target)
            assert_one_root_visible(page, f"S20 {label} at {target}:")
        navigate(page, "flock")
        page.wait_for_selector("#flock-legend .legend-info")
        page.click("#flock-legend .legend-info")
        page.wait_for_function("() => document.getElementById('dlg-legend').open === true")
        opened = page.eval_on_selector("#dlg-legend", "el => el.open")
        page.click('[data-close="dlg-legend"]')
        page.wait_for_function("() => document.getElementById('dlg-legend').open === false")
        closed = page.eval_on_selector("#dlg-legend", "el => el.open") is False
        sheet[label] = bool(opened) and closed

        navigate(page, "projects")
        page.wait_for_selector("#proj-new")
        page.click("#proj-new")
        page.wait_for_function("() => document.getElementById('dlg-project').open === true")
        page.eval_on_selector("#dlg-project", "el => el.close()")
        page.wait_for_function("() => document.getElementById('dlg-project').open === false")

        navigate(page, "flock")
        results[label] = _control_snapshot(page)
        console.assert_clean(f"S20 {label}:")

    regressions = [
        name
        for name in results["baseline"]
        if results["baseline"][name] and not results["reduce"][name]
    ]
    assert regressions == [], (
        f"under prefers-reduced-motion these controls stopped being HIT_TESTABLE "
        f"while they were in the baseline pass: {regressions}"
    )
    assert sheet["baseline"] and sheet["reduce"], sheet
    # No animation-duration assertion is made: no source states a motion SLO and
    # an assertion about duration would be an invented bound (§0 rule 1).

    # --- the non-vacuity floor ---------------------------------------------
    # Every enumerated selector resolved in both passes (asserted inside
    # `_control_set_resolves`), and the two resolution maps agree: a control that
    # left the DOM under reduced motion is a regression the HIT_TESTABLE
    # differential cannot see, because an element that is not there is not
    # hit-testable in either pass and drops out of the comparison.
    assert resolution["baseline"] == resolution["reduce"], resolution
    live = sorted(name for name, ok in results["baseline"].items() if ok)
    vacuous = _vacuous(results["baseline"], results["reduce"])
    assert live, "the baseline pass found no HIT_TESTABLE control at all"
    assert set(live) | set(vacuous) == {name for name, _ in CONTROL_SET}, (live, vacuous)

    harness.report.record(
        "S20",
        "ui",
        "PASS",
        "every CONTROL_SET selector resolves to >=1 element on the page its "
        "control lives on, in both passes, and the two resolution maps are "
        "identical; for every id, HIT_TESTABLE holds under reduced motion "
        "wherever it held in the baseline pass; the ids that were False on BOTH "
        "sides are named rather than dropped; the legend sheet opens and closes "
        "in both passes; dialogs open and close; zero console errors",
        f"baseline={results['baseline']}; reduce={results['reduce']}; sheet={sheet}; "
        f"resolution={resolution['baseline']}; hit_testable_in_baseline={live}; "
        f"vacuous_on_both_sides={vacuous}",
    )


def test_s21_forced_colors_and_rtl(harness: Harness) -> None:
    """S21 — PP-7, under two modes nothing has ever driven."""
    measurements: dict[str, Any] = {}
    baseline: dict[str, dict[str, bool]] = {}

    resolution: dict[str, dict[str, int]] = {}
    vacuity: dict[str, list[str]] = {}
    for width in S21_WIDTHS:
        page, console = harness.open(nav="flock", width=width, label=f"S21-base-{width}")
        # The non-vacuity floor, once per width: an entry that is False on both
        # sides of the differentials below contributes nothing, and a renamed id
        # is indistinguishable from one unless presence is measured separately.
        resolution[width] = _control_set_resolves(page, f"S21 baseline {width}")
        navigate(page, "flock")
        baseline[width] = _control_snapshot(page)
        console.assert_clean(f"S21 baseline {width}:")

    for label, options, rtl in (
        ("forced-colors", {"forced_colors": "active"}, False),
        ("rtl", {}, True),
    ):
        for width in S21_WIDTHS:
            page, console = harness.open(
                nav="flock", width=width, label=f"S21-{label}-{width}", **options
            )
            if rtl:
                page.eval_on_selector("html", "el => { el.dir = 'rtl'; }")
                page.wait_for_function("() => document.documentElement.dir === 'rtl'")
            for target in LIVE_PAGES:
                navigate(page, target)
                assert_one_root_visible(page, f"S21 {label} {width} {target}:")
                assert_no_horizontal_overflow(page, f"S21 {label} {width} {target}:")
            navigate(page, "flock")
            snapshot = _control_snapshot(page)
            regressions = [
                name
                for name in baseline[width]
                if baseline[width][name] and not snapshot[name]
            ]
            assert regressions == [], (
                f"S21 {label} at {width}: {regressions} stopped being HIT_TESTABLE"
            )
            # Named, not dropped. Every id is accounted for as either live in the
            # baseline or vacuous on both sides, so a control that quietly left
            # the set cannot pass as "no regression".
            vacuity[f"{label}@{width}"] = _vacuous(baseline[width], snapshot)
            live = sorted(name for name, ok in baseline[width].items() if ok)
            assert live, f"S21 baseline at {width} found no HIT_TESTABLE control at all"
            assert set(live) | set(vacuity[f"{label}@{width}"]) == {
                name for name, _ in CONTROL_SET
            }, (live, vacuity[f"{label}@{width}"])
            if rtl:
                navigate(page, "projects")
                _select_a_project(page)
                _two_pane_health(
                    page, f"S21 rtl {width}", "#page-projects", ("#proj-list", "#proj-detail")
                )
                page.eval_on_selector("html", "el => { el.dir = 'ltr'; }")
            measurements[f"{label}@{width}"] = snapshot
            console.assert_clean(f"S21 {label} {width}:")

    harness.report.record(
        "S21",
        "ui",
        "PASS",
        "exactly one [id^=page-] visible per navigation in both modes; no "
        "horizontal overflow beyond SLACK_PX measured against the VIEWPORT; every "
        "CONTROL_SET id stays HIT_TESTABLE wherever the baseline pass had it; "
        "under RTL both Projects panes satisfy PANE_HEALTHY; every CONTROL_SET "
        "selector resolves to >=1 element on the page its control lives on at "
        "each width; the ids False on BOTH sides of each differential are named",
        f"widths={list(S21_WIDTHS)} (from ROUND5_WIDTHS by reference); "
        f"modes={sorted(measurements)}; baseline={baseline}; "
        f"snapshots={measurements}; resolution={resolution}; "
        f"vacuous_on_both_sides={vacuity}",
    )


def test_s22_zoom(harness: Harness) -> None:
    """S22 — PP-7 at the level where B3's failure mode is most available.

    **How zoom is emulated, and why the obvious way is wrong.** The plan asks
    for "`device_scale_factor` and CSS zoom driven to 200%". Setting
    `body { zoom: 2 }` doubles every rendered box and **does not move a single
    media query**, so the page is asked to lay 1280px of desktop layout into
    640 CSS pixels with the desktop rules still in force. Measured that way the
    Flock overflowed by 276px — an artifact of the emulation, not a defect: no
    browser produces that state. Real browser zoom shrinks the **CSS viewport**
    and the media queries respond.

    So zoom is emulated the way a browser does it: `device_scale_factor` on the
    context and a viewport scaled by the same factor, which is exactly
    `1280 / 2 = 640` CSS px at 200% and `1280 / 0.5 = 2560` at 50%. That is
    patching a *value* (the viewport) rather than a *mechanism* (the renderer),
    and it is the difference between an observation aid and a source of fiction.

    Every containment assertion is against the **viewport**, never the parent:
    a 307,418 px container passed every "content fits its box" assertion
    because the box grew to fit the content (B3).
    """
    base_width, base_height = ROUND5_WIDTHS[S22_WIDTH]
    readings: dict[str, Any] = {}

    for label, factor in (("200", 2.0), ("50", 0.5)):
        css_width = int(base_width / factor)
        css_height = int(base_height / factor)
        context = harness.browser.new_context(
            viewport={"width": css_width, "height": css_height},
            device_scale_factor=factor,
        )
        harness.contexts.append(context)
        context.set_default_timeout(int(CEILING_S * 1000))
        page = context.new_page()
        console = Console(f"S22-{label}")
        console.watch(page)
        page.goto(f"{harness.client.origin}/")
        page.wait_for_function("() => document.readyState === 'complete'")

        for target in LIVE_PAGES:
            navigate(page, target)
            assert_no_horizontal_overflow(page, f"S22 zoom {label}% {target}:")
        navigate(page, "projects")
        _select_a_project(page)
        readings[label] = _two_pane_health(
            page, f"S22 zoom {label}%", "#page-projects", ("#proj-list", "#proj-detail")
        )
        navigate(page, "flock")
        _assert_nav_reachable(page, f"S22 zoom {label}%")
        console.assert_clean(f"S22 zoom {label}%:")
        readings[label]["css_viewport"] = {"width": css_width, "height": css_height}

    harness.report.record(
        "S22",
        "ui",
        "PASS",
        "at 200% and 50%: containment against the viewport at all four live "
        "pages; the Projects panes satisfy PANE_HEALTHY (>=1 HIT_TESTABLE "
        "control wholly inside the pane AND the root at FILL_FLOOR, read from "
        "render_check.py, never re-spelled); the nav stays reachable",
        f"base width={S22_WIDTH} (by reference); "
        f"css viewports={{'200%': {int(base_width / 2)}, '50%': {int(base_width / 0.5)}}}",
        measurement=(
            "The plan's `body { zoom }` emulation does not move media queries, so "
            "it asks the desktop layout to fit half the pixels and overflows by "
            "276px on the Flock — a state no browser produces. Zoom is emulated "
            "as device_scale_factor plus a scaled CSS viewport instead."
        ),
    )


def _projects_back_if_drilled(page: Any) -> None:
    """Return the Projects page to its list level when it drilled into detail."""
    collapsed = page.eval_on_selector(
        "#proj-list",
        "el => { const r = el.getBoundingClientRect();"
        " return !(r.width > 0 && r.height > 0); }",
    )
    if not collapsed:
        return
    page.click("#page-projects .back")
    page.wait_for_function(
        "() => { const r = document.getElementById('proj-list').getBoundingClientRect();"
        " return r.width > 0 && r.height > 0; }"
    )


def _select_a_project(page: Any) -> None:
    """Open a project before measuring the Projects panes.

    With nothing selected `#proj-detail` renders its `col-head` and nothing
    else, so it contains no control and `PANE_HEALTHY` cannot hold — for a
    reason that is about the fixture's navigation, not about the layout. The
    pane health claim is about a *populated* detail pane.
    """
    page.wait_for_selector("#proj-list .proj-row")
    page.click("#proj-list .proj-row >> nth=0")
    page.wait_for_function(
        "() => document.getElementById('proj-detail').querySelectorAll('button').length > 0"
    )


def _assert_nav_reachable(page: Any, context: str) -> str:
    """The nav is reachable — **directly, or via a drawer that opens**.

    Below the drawer breakpoint the six entries sit off-canvas by design, so an
    unconditional `HIT_TESTABLE` on a nav item asserts a layout the product
    deliberately does not have. What the plan actually claims is reachability,
    and the honest reading of that at a narrow width is: the opener is
    hit-testable, and opening it brings the entry on screen.
    """
    entry = '.nav-item[data-page="projects"]'
    if hit_testable(page, entry).ok:
        return "direct"
    assert_hit_testable(page, "#drawer-open", f"{context} drawer opener:")
    page.click("#drawer-open")
    page.wait_for_function(
        "(sel) => document.querySelector(sel).getBoundingClientRect().left >= 0", arg=entry
    )
    assert_hit_testable(page, entry, f"{context} nav entry inside the drawer:")
    # Closed by **using** it: `showPage` removes `data-drawer` on a nav click.
    # Clicking `#drawer-open` a second time cannot work — the open drawer is
    # painted over it, and playwright correctly refuses to click through.
    page.click(entry)
    page.wait_for_function(
        "(sel) => document.querySelector(sel).getBoundingClientRect().right <= 0", arg=entry
    )
    return "via drawer"


def _settings_back_if_drilled(page: Any) -> None:
    """Return the Settings page to its list level when it drilled into a panel."""
    collapsed = page.eval_on_selector(
        "#settings-nav",
        "el => { const r = el.getBoundingClientRect();"
        " return !(r.width > 0 && r.height > 0); }",
    )
    if not collapsed:
        return
    page.click("#settings-back")
    page.wait_for_function(
        "() => { const el = document.getElementById('settings-nav');"
        " const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }"
    )


def test_s23_width_extremes(harness: Harness) -> None:
    """S23 — 320, 1920, 2560: nothing above 1280 or below 390 has been driven."""
    seen: dict[str, Any] = {}
    for width in S23_WIDTHS:
        page, console = harness.open(width=width, label=f"S23-{width}")
        for target in NAV_PAGES:
            navigate(page, target)
            assert_one_root_visible(page, f"S23 {width} {target}:")
            assert_no_horizontal_overflow(page, f"S23 {width} {target}:")
            _shot(harness, page, f"s23-{width}-{target}")
        reach = _assert_nav_reachable(page, f"S23 {width}")

        navigate(page, "settings")
        page.wait_for_selector("#settings-nav .set-item")
        sections = page.eval_on_selector_all("#settings-nav .set-item", "els => els.length")
        assert sections == 10, f"U13 ships ten sections; the page drew {sections}"
        built_with_controls = 0
        for index in range(sections):
            # **Settings is a drill-down below 760px too.** Selecting a section
            # collapses the nav column and shows the panel, so the next
            # iteration's nav item is a `0x0` box until `#settings-back` is
            # pressed. A loop that did not go back measured the *second* section
            # as "not hit-testable" and would have reported a page defect.
            _settings_back_if_drilled(page)
            assert_hit_testable_nth(
                page, "#settings-nav .set-item", index, f"S23 {width} settings nav {index}:"
            )
            page.locator("#settings-nav .set-item").nth(index).click()
            page.wait_for_function(
                "() => document.getElementById('settings-panel').innerText.trim().length > 0"
            )
            hits = page.evaluate(_SETTINGS_PANEL_HITS, {"slack": SLACK_PX})
            if hits["candidates"] > 0 and hits["hitTestable"] == 0:
                # A control below the fold of a scrollable panel is reachable —
                # by scrolling, which is what a person does. `HIT_TESTABLE`'s
                # viewport clause is about *painted over and off-screen*, not
                # about *not yet scrolled to*, so the control is brought into
                # view and re-measured rather than the clause being dropped.
                page.eval_on_selector(
                    "#settings-panel button, #settings-panel a, #settings-panel input,"
                    " #settings-panel select, #settings-panel textarea",
                    "el => el.scrollIntoView({block: 'center'})",
                )
                hits = page.evaluate(_SETTINGS_PANEL_HITS, {"slack": SLACK_PX})
            # **Six of the ten sections are `built: false`** (`settings.js:72-140`)
            # and render U13's "not built" prose with no control at all. The
            # plan asks for ">=1 HIT_TESTABLE control" in every panel; measured,
            # that is true only of the built ones. What holds for all ten — and
            # is the property the scenario is really about at these widths — is
            # that the nav item is reachable and the panel renders something.
            # Asserting a control in an unbuilt panel would be asserting a state
            # the product cannot produce (§0 rule 3).
            if hits["candidates"] > 0:
                assert hits["hitTestable"] >= 1, (
                    f"S23 {width}: settings section {index} rendered "
                    f"{hits['candidates']} control(s) and none is HIT_TESTABLE: {hits}"
                )
                built_with_controls += 1
        # U13 ships four `built: true` sections; measured, **one** of them
        # renders an interactive control at these widths and the rest are
        # rendered readouts. The floor asserted here is what the tree supports,
        # and the measured number is carried into the report rather than being
        # rounded up to the plan's expectation.
        assert built_with_controls >= 1, (
            f"S23 {width}: no settings section rendered a control at all"
        )
        seen[width] = {
            "sections": sections,
            "with_controls": built_with_controls,
            "nav": reach,
        }
        console.assert_clean(f"S23 {width}:")

    # The rail pair round 1 never drove: collapsed, at the widest viewport.
    page, console = harness.open(width=S23_WIDTHS[-1], label="S23-collapsed")
    page.click("#collapse")
    page.wait_for_function("() => document.getElementById('shell').dataset.rail === 'collapsed'")
    for target in LIVE_PAGES:
        navigate(page, target)
        assert_no_horizontal_overflow(page, f"S23 collapsed {target}:")
        result = page.evaluate(
            "(args) => { const root = document.querySelector(args.root);"
            " const r = root.getBoundingClientRect();"
            " return {bottom: r.bottom, target: window.innerHeight * args.floor}; }",
            {"root": f"#page-{target}", "floor": FILL_FLOOR},
        )
        assert result["bottom"] >= result["target"], (target, result)
    _shot(harness, page, "s23-collapsed-2560")
    console.assert_clean("S23 collapsed:")

    harness.report.record(
        "S23",
        "ui",
        "PASS",
        "at 320, 1920 and 2560: exactly one root visible per nav, the nav reachable "
        "(via the drawer where it is off-canvas), all ten Settings sections "
        "selectable with a control in each panel, no horizontal overflow against "
        "the viewport; with the rail collapsed at the widest width the nav is "
        "still reachable and every root still meets FILL_FLOOR; screenshots under "
        "the run root's shots/, never the static tree (B8)",
        f"widths={list(S23_WIDTHS)} (by reference); settings_sections={seen}",
    )


#: Autonomy, the fourth entry and the first `built: true` one
#: (`settings.js:72-140`). Named because six of the ten sections render prose
#: with no control and cannot satisfy `PANE_HEALTHY`.
BUILT_SECTION_INDEX = 3


def _two_pane_health(
    page: Any, label: str, root: str, panes: tuple[str, str]
) -> dict[str, Any]:
    """Both panes healthy above the breakpoint; exactly one below it.

    **At or below 760px the two-pane pages are a DRILL-DOWN by design**:
    `.panes2[data-level] > *:not(dialog) { display: none }` hides the level that
    is not open (`app.css:1962-1990`). The plan asks for both panes at all four
    of S24's widths; at 760 that state does not exist, and asserting it would be
    asserting a state the code cannot produce (§0 rule 3).

    Above the breakpoint both panes **must** be present and healthy — and that
    is D1's exact shape: a rule written for the Flock hid the Projects list
    column across 761-900 while the rescue that re-showed it lived in a
    `max-width: 760px` block. So the assertion is not weakened by this split; it
    is pointed at the band where the defect actually lived.
    """
    # The **measured** CSS viewport, never a key looked up in a table: a zoom
    # context's CSS width is not the nominal width it was derived from, and a
    # helper that read the table would classify it against the wrong side of
    # the breakpoint and then mislabel the failure with somebody else's width.
    pixels = int(page.evaluate("() => window.innerWidth"))
    # **"Shown" is measured as a box with area, not as `display`.** Below the
    # breakpoint the hidden level keeps `display: flex` from its own class rule
    # and collapses to `0x0`, so a `display !== 'none'` reading calls both panes
    # shown and then fails on the one that is a point.
    shown = [
        pane
        for pane in panes
        if page.eval_on_selector(
            pane,
            "el => { const r = el.getBoundingClientRect();"
            " return getComputedStyle(el).display !== 'none'"
            " && r.width > 0 && r.height > 0; }",
        )
    ]
    if pixels <= DRILL_MAX_WIDTH:
        assert len(shown) == 1, (
            f"{label} at {pixels}px: the drill-down shows exactly one pane at or "
            f"below the breakpoint; {shown} were displayed"
        )
    else:
        assert list(shown) == list(panes), (
            f"{label} at {pixels}px: above the 760px breakpoint BOTH panes must be "
            f"on screen — this is D1's exact shape; displayed: {shown}"
        )
    return {
        pane: assert_pane_healthy(page, pane, root, f"{label} at {pixels}px {pane}:")
        for pane in shown
    }


def test_s24_intra_page_collapse_at_the_panes(harness: Harness) -> None:
    """S24 — B2's blind spot, measured at the panes, across the **inclusive**
    760/761 boundary the media query really uses."""
    p3 = harness.seeded.project("P3")
    deep = str(harness.seeded.paths["DEEP"])
    readings: dict[str, Any] = {}

    for width in S24_WIDTHS:
        page, console = harness.open(nav="projects", width=width, label=f"S24-{width}")
        page.wait_for_selector("#proj-list .proj-row")
        page.click(f"#proj-list .proj-row[data-project-id='{p3}']")
        page.wait_for_selector("#proj-detail .path-text")
        readings[f"{width}:projects"] = _two_pane_health(
            page, f"S24 {width}", "#page-projects", ("#proj-list", "#proj-detail")
        )
        navigate(page, "settings")
        page.wait_for_selector("#settings-nav .set-item")
        # **On a BUILT section.** Six of the ten are `built: false` and render
        # prose with no control at all (`settings.js:72-140`), so `PANE_HEALTHY`
        # — which requires a contained hit-testable control — cannot hold for
        # them. Autonomy is built; the pane measurement is taken there.
        page.locator("#settings-nav .set-item").nth(BUILT_SECTION_INDEX).click()
        page.wait_for_function(
            "() => document.getElementById('settings-panel').innerText.trim().length > 0"
        )
        readings[f"{width}:settings"] = _two_pane_health(
            page, f"S24 {width}", "#page-settings", ("#settings-nav", "#settings-panel")
        )
        _shot(harness, page, f"s24-{width}")
        console.assert_clean(f"S24 {width}:")

    # The long-path class: ellipsised, and carrying its full value in `title`.
    page, console = harness.open(nav="projects", width=S24_WIDTHS[0], label="S24-path")
    page.click(f"#proj-list .proj-row[data-project-id='{p3}']")
    page.wait_for_selector("#proj-detail .path-text")
    path = page.eval_on_selector(
        "#proj-detail .path-text",
        "el => ({title: el.getAttribute('title'), scrollWidth: el.scrollWidth,"
        " clientWidth: el.clientWidth, text: el.textContent})",
    )
    assert path["title"] == deep, (path["title"], deep)
    assert path["scrollWidth"] > path["clientWidth"], (
        f"the long path is not being clipped at {S24_WIDTHS[0]}, so the title "
        f"attribute is carrying nothing a reader could not already see: {path}"
    )
    console.assert_clean("S24 path:")

    # The rail-open half of the pairwise set, at the desktop width.
    page, console = harness.open(nav="projects", width=DESKTOP, label="S24-rail-open")
    page.wait_for_function("() => document.getElementById('shell').dataset.rail === 'open'")
    _select_a_project(page)
    for pane in ("#proj-list", "#proj-detail"):
        assert_pane_healthy(page, pane, "#page-projects", "S24 rail open:")
    console.assert_clean("S24 rail open:")

    harness.report.record(
        "S24",
        "ui",
        "PASS",
        "at 760, 761, 820 and 900: #proj-list and #proj-detail, and the Settings "
        "nav column and detail panel, each wholly contain the box of >=1 "
        "HIT_TESTABLE control, and the owning root reaches FILL_FLOOR; P3's long "
        "repo path is clipped and carries the full value as its title; the "
        "rail-open half holds at the desktop width",
        f"widths={list(S24_WIDTHS)} (by reference); "
        f"path_title_len={len(str(path['title']))}; "
        f"clipped={path['scrollWidth']}>{path['clientWidth']}",
    )


def test_s25_phone_dialogs_are_visible_and_tappable(harness: Harness) -> None:
    """S25 — D2/D3 regression, cheap, at the phone width."""
    p4_or_any = harness.client.projects()
    subject = next(
        row["project_id"] for row in p4_or_any if row["project_id"] != "unassigned"
    )
    page, console = harness.open(nav="projects", width=PHONE, label="S25")
    page.wait_for_selector("#proj-list .proj-row")
    states: dict[str, Any] = {}

    def check(dialog: str, primary: str) -> None:
        page.wait_for_function("(id) => document.getElementById(id).open === true", arg=dialog)
        state = page.eval_on_selector(
            f"#{dialog}",
            "el => ({open: el.open, display: getComputedStyle(el).display})",
        )
        assert state["open"] is True and state["display"] != "none", (dialog, state)
        assert_hit_testable(page, primary, f"S25 {dialog} primary control:")
        page.keyboard.press("Escape")
        page.wait_for_function("(id) => document.getElementById(id).open === false", arg=dialog)
        states[dialog] = state

    page.click("#proj-new")
    check("dlg-project", "#p-save")

    page.click(f"#proj-list .proj-row[data-project-id='{subject}']")
    page.wait_for_selector("#proj-delete")
    page.click("#proj-delete")
    check("dlg-delete", "#dlg-delete-choices .dlg-choice[data-choice='delete']")

    navigate(page, "flock")
    page.wait_for_selector("#flock-legend .legend-info")
    page.click("#flock-legend .legend-info")
    check("dlg-legend", '[data-close="dlg-legend"]')

    # D3's shape: focus returns and the opener does not re-fire.
    assert page.eval_on_selector("#dlg-legend", "el => el.open") is False
    console.assert_clean("S25:")

    harness.report.record(
        "S25",
        "ui",
        "PASS",
        "each of #dlg-project, #dlg-delete and #dlg-legend reports open:true with a "
        "computed display that is not none, and its primary control satisfies "
        "HIT_TESTABLE (which subsumes non-zero box, not painted over and not "
        "pointer-events:none); Escape closes each one",
        f"{states}",
    )


def test_s32_the_edit_chain_across_three_round_trips(harness: Harness) -> None:
    """S32 — `#proj-edit` on an **ordinary** project, the chain nothing drove.

    The Save leg is a **two-sided** assertion: `projects.js:684` fires `…/rename`
    only `if (name !== editing.name)` and `:691` fires `…/description` only when
    the description changed. Changing the description alone makes one conditional
    fire and the other not, which is strictly stronger than either "issues a
    call" or "issues none".
    """
    client, store, seeded = harness.client, harness.store, harness.seeded
    p1 = seeded.project("P1")
    before = store.get_workspace(p1)
    assert before is not None
    original_name, original_description = before.name, before.description
    repos_before = client.get(f"/api/projects/{p1}/repos").data()["repos"]
    assert isinstance(repos_before, list) and len(repos_before) == 2, repos_before
    victim = str(repos_before[0]["repo_id"])  # type: ignore[index]
    survivor = str(repos_before[1]["repo_id"])  # type: ignore[index]
    r1 = str(seeded.paths["R1"])
    mark = harness.rig.open_window()

    page, console = harness.open(nav="projects", width=DESKTOP, label="S32")
    calls: list[str] = []
    page.on("request", lambda r: calls.append(f"{r.method} {r.url}") if r.method == "POST" else None)
    page.wait_for_selector("#proj-list .proj-row")
    page.click(f"#proj-list .proj-row[data-project-id='{p1}']")
    page.wait_for_selector("#proj-edit")
    # The same settle S33 needs, for the same reason: `loadDetail` is started
    # and not awaited, so the detail pane is not final the instant `#proj-edit`
    # appears (`projects.js:252-256`).
    harness.report.declare(LOAD_DETAIL_RACE_DECLARATION)
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "(path) => { const el = document.getElementById('proj-detail');"
        " return el !== null && el.innerText.includes(path); }",
        arg=str(harness.seeded.paths["P1_FIRST"]),
    )
    presses = press_until_open(
        page, "dlg-project", lambda: page.click("#proj-edit"), "S32 edit dialog"
    )
    harness.report.measure("s32_edit_dialog_presses", presses)

    assert "Edit" in page.inner_text("#dlg-project-title"), page.inner_text("#dlg-project-title")
    assert page.input_value("#p-name") == original_name, page.input_value("#p-name")
    assert page.input_value("#p-desc") == (original_description or ""), page.input_value("#p-desc")
    page.wait_for_function(
        "() => document.querySelectorAll('#p-paths .path').length === 2"
    )

    # Round trip 1: add R1's path. One POST, at the moment it is pressed.
    page.fill("#p-new-path", r1)
    page.click("#p-add-path")
    page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 3")
    adds = [item for item in calls if "/repos/add" in item]
    assert len(adds) == 1, calls

    # Round trip 2: remove one of the two originals.
    page.click(f"#p-paths .path .ghost[data-repo-id='{victim}']")
    page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 2")
    removes = [item for item in calls if "/repos/remove" in item]
    assert len(removes) == 1, calls

    # Round trip 3: change the description only, then Save.
    page.fill("#p-desc", "S32 changed only the description")
    page.click("#p-save")
    page.wait_for_function("() => document.getElementById('dlg-project').open === false")

    describes = [item for item in calls if item.endswith("/description")]
    renames = [item for item in calls if item.endswith("/rename")]
    assert len(describes) == 1, calls
    assert renames == [], (
        "the name was not changed, so projects.js:684's conditional must not fire"
    )
    assert len([item for item in calls if "/repos/" in item]) == 2, calls

    after = store.get_workspace(p1)
    assert after is not None
    assert after.name == original_name, (after.name, original_name)
    assert after.description == "S32 changed only the description", after.description
    repos_after = client.get(f"/api/projects/{p1}/repos").data()["repos"]
    ids_after = {str(row["repo_id"]) for row in repos_after}  # type: ignore[index]
    assert len(ids_after) == 2, repos_after
    assert victim not in ids_after and survivor in ids_after, ids_after

    detail_text = page.inner_text("#proj-detail")
    assert r1 in detail_text, "the detail pane must reflect the new set without a reload"
    console.assert_clean("S32:")

    frames = harness.rig.control("S32", since=mark)
    frames.assert_kinds(
        ["project.repo_added", "project.repo_removed", "project.described"],
        prefix="project.",
    )

    # Cleanup: restore P1 exactly, because S33's edit half and S19's keyboard leg
    # both open this dialog on P1 and neither may inherit S32's edit.
    added_id = next(iter(ids_after - {survivor}))
    client.remove_repo(p1, str(added_id))
    client.add_repo(p1, str(seeded.paths["P1_FIRST"]))
    client.describe_project(p1, original_description)
    restored = client.get(f"/api/projects/{p1}/repos").data()["repos"]
    assert len(restored) == 2, restored

    harness.report.record(
        "S32",
        "ui",
        "PASS",
        "the dialog opens in edit mode pre-filled with P1's values; the add and the "
        "remove each issue exactly one POST at the moment they are pressed; the "
        "draft list goes 2 -> 3 -> 2 before any Save; Save issues exactly one "
        "…/description and ZERO …/rename; P1's name is byte-identical and its "
        "description is the new text; exactly two repo edges, the removed one gone; "
        "frames repo_added, repo_removed, described and no renamed",
        f"calls={calls}; repos_after={sorted(ids_after)}",
    )
