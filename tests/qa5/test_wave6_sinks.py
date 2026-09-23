"""Wave 6 — the sinks, the races, the refusals, the degradation and the gates.

Order inside the wave is fixed: **S26, S27, S28, S33, S34, S30, S31, then S29
last** — S29 stops the server and everything that needs it must have run.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .auditprobe import assert_shape
from .conftest import Console, Harness, navigate, press_until_open
from .constants import DESKTOP
from .dom import VIEWPORTS
from .report import AC28_DECLARATION, LOAD_DETAIL_RACE_DECLARATION
from .runroot import HarnessBlocked
from .wire import assert_generic_error, await_true

REPO = Path("/root/Shepherd")

#: How long the page is given to notice a dropped stream. A harness liveness
#: bound, not a product SLO: no source states one.
STREAM_NOTICE_CEILING_S = 30.0


def test_wave6_reproves_the_rig(harness: Harness) -> None:
    window = harness.rig.reprove("6")
    for name in ("A", "B"):
        assert [frame.kind for frame in window.control[name]] == [
            "project.created",
            "project.deleted",
        ], name


def test_s26_the_production_audit_sink_on_disk(harness: Harness) -> None:
    """S26 — PP-6, read off **disk**, not out of a fixture's list.

    The prior claim that "two autonomy POSTs append two audit rows" was
    *reasoned*: every earlier test used a chokepoint fixture that collects into
    a Python list and never touches a file. This is the first time the shipped
    `RotatingJsonlLog` has been read.
    """
    client, store = harness.client, harness.store
    assert client.get("/api/autonomy").data()["level"] == 2

    doomed = client.create_project("S26-target")
    target = str(doomed["project"]["project_id"])  # type: ignore[index]

    mark = harness.audit.mark()
    frame_mark = harness.rig.open_window()

    assert client.post("/api/autonomy", {"level": 3}).status == 200
    assert client.post("/api/autonomy", {"level": 2}).status == 200
    deleted = client.delete_project(target)
    assert deleted["deleted"] is True, deleted

    # Counted to the moment **before** the control runs (§3a footprint rule):
    # the control is two further gated invokes and they are asserted separately.
    records = harness.audit.mutations_since(mark)
    tools = [str(row.get("tool")) for row in records]
    assert tools == ["set_autonomy_level", "set_autonomy_level", "delete_project"], tools
    assert_shape(records)
    for record in records:
        assert isinstance(record.get("args"), dict), record

    assert client.get("/api/autonomy").data()["level"] == 2
    assert store.get_app_state("autonomy_level") == 2, store.get_app_state("autonomy_level")
    assert store.get_workspace(target) is None

    # D25: a log that silently stopped writing is the failure the counter exists
    # to prevent. `RotatingJsonlLog.lost` is not reachable from here — the sink
    # owns it — but every lost line is counted as `audit_line_lost` in the store.
    assert store.list_anomaly_counts().get("audit_line_lost", 0) == 0, (
        "the audit sink reported lost lines; the record count above is a floor, "
        "not a measurement"
    )

    control_mark = harness.audit.mark()
    window = harness.rig.control("S26", since=frame_mark)
    window.assert_kinds(["project.deleted"], prefix="project.")
    control_records = harness.audit.mutation_tools_since(control_mark)
    assert control_records == ["create_project", "delete_project"], control_records

    destructive = records[-1]
    harness.report.record(
        "S26",
        "integration",
        "PASS",
        "exactly three new JSONL records for the three calls under test, in order, "
        "each with at/tool/decision/approved_by and a mapping of redacted args; "
        "GET /api/autonomy reads back 2; the project is gone; audit_line_lost is 0; "
        "one project.deleted frame and zero for the two autonomy POSTs; the "
        "control's own two gated invokes are asserted separately",
        f"tools={tools}; delete record decision={destructive.get('decision')!r} "
        f"approved_by={destructive.get('approved_by')!r}; control={control_records}",
        records=[{k: v for k, v in row.items() if k != "args"} for row in records],
        measured_claim=(
            "approved_by for the destructive call is "
            f"{destructive.get('approved_by')!r} — policy.TABLE allows "
            "LOCAL_DESTRUCTIVE for Audience.HUMAN at both autonomy levels."
        ),
    )


def test_s27_ordering_and_coalescing_under_real_concurrency(harness: Harness) -> None:
    """S27 — PP-1 **and** PP-8: two real threads, two real readers.

    Every prior "concurrency" test was two synchronous `click()` calls on one
    thread. This is ten mutations from two threads while both clients read.
    """
    client = harness.client
    # The mark is taken **before** the creates and their ten frames are awaited,
    # so the window opened afterwards cannot inherit one of them. A mark taken
    # the instant the last POST returns races the reader threads, and a create
    # then lands inside the window asserted to hold exactly ten renames and
    # descriptions.
    settle = harness.rig.open_window()
    targets = [
        str(client.create_project(f"S27-{index}")["project"]["project_id"])  # type: ignore[index]
        for index in range(10)
    ]
    for name in ("A", "B"):
        harness.rig.await_count(settle, 10, name)
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    def rename(project_id: str) -> None:
        client.rename_project(project_id, f"S27-renamed-{project_id[-4:]}")

    def describe(project_id: str) -> None:
        client.describe_project(project_id, f"described {project_id[-4:]}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(rename, project_id) for project_id in targets[:5]]
        futures += [pool.submit(describe, project_id) for project_id in targets[5:]]
        for future in futures:
            future.result()

    per_client: dict[str, list[int]] = {}
    for name in ("A", "B"):
        frames = harness.rig.await_count(mark, 10, name)
        assert len(frames) == 10, [frame.kind for frame in frames]
        seqs = [frame.seq for frame in frames]
        assert seqs == sorted(seqs), (name, seqs)
        assert len(set(seqs)) == 10, f"client {name} saw a duplicate id: {seqs}"
        per_client[name] = seqs
    assert set(per_client["A"]) == set(per_client["B"]), per_client

    for project_id in targets[:5]:
        row = harness.store.get_workspace(project_id)
        assert row is not None and row.name.startswith("S27-renamed-"), row
    for project_id in targets[5:]:
        row = harness.store.get_workspace(project_id)
        assert row is not None and row.description is not None, row

    assert len(harness.audit.mutations_since(audit_mark)) == 10

    # The third observer tab, counted at the same named seam as S18.
    page, console = harness.open(nav="projects", width=DESKTOP, label="S27-observer")
    await_true(
        lambda: page.inner_text("#stream-status").strip().lower() == "live",
        "the observer tab's stream never reached `live`, so a refresh count would "
        "be a count of nothing",
    )
    reads: list[str] = []
    page.on(
        "request",
        lambda request: reads.append(request.url)
        if request.method == "GET" and "/api/projects" in request.url
        else None,
    )
    burst_mark = harness.rig.open_window()
    client.rename_project(targets[0], "S27-burst")
    harness.rig.await_kind(burst_mark, "project.renamed", "B")
    # **The DOM is the observation; the request count is the coalescing claim.**
    # Waiting on the request count alone cannot tell "the page never heard the
    # envelope" from "the page heard it and answered from somewhere else".
    page.wait_for_function(
        "() => document.getElementById('proj-list').innerText.includes('S27-burst')"
    )
    list_reads = [url for url in reads if url.rstrip("/").endswith("/api/projects")]
    assert len(list_reads) <= 2, (
        f"refreshAll ran {len(list_reads)} list passes for one envelope: {reads}"
    )
    console.assert_clean("S27:")

    window = harness.rig.control("S27", since=mark)
    for name in ("A", "B"):
        assert [frame.kind for frame in window.control[name]] == [
            "project.created",
            "project.deleted",
        ], name

    for project_id in targets:
        client.delete_project(project_id)

    harness.report.record(
        "S27",
        "e2e_backend",
        "PASS",
        "each client receives exactly ten frames with strictly increasing id: and "
        "no duplicate; the two clients' frame sets are equal; ten mutations landed "
        "with no lost update; ten audit records; an observer tab runs refreshAll at "
        "most twice per burst, counted at page.on('request')",
        f"A={per_client['A']}; B={per_client['B']}; observer_reads={len(reads)}",
    )


def test_s28_double_submit_at_a_real_browser(harness: Harness) -> None:
    """S28 — the in-flight **flag** guard, deliberately not `disabled`."""
    client = harness.client
    before = len(client.projects())
    mark = harness.rig.open_window()

    page, console = harness.open(nav="projects", width=DESKTOP, label="S28")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    page.wait_for_selector("#proj-new")
    page.click("#proj-new")
    page.wait_for_function("() => document.getElementById('dlg-project').open === true")
    page.fill("#p-name", "S28-once")
    # Two clicks in one tick: the guard is an in-flight flag and not `disabled`,
    # because the nodes are rebuilt on every answer.
    page.eval_on_selector(
        "#p-save", "el => { el.click(); el.click(); }"
    )
    page.wait_for_function("() => document.getElementById('dlg-project').open === false")

    creates = [url for url in posts if url.rstrip("/").endswith("/api/projects")]
    assert len(creates) == 1, f"two clicks in one tick produced {len(creates)} POSTs: {posts}"
    rows = [row for row in client.projects() if row.get("name") == "S28-once"]
    assert len(rows) == 1, rows
    assert len(client.projects()) == before + 1
    page.wait_for_selector("#proj-list .proj-row[data-project-id='%s']" % rows[0]["project_id"])

    # The composer's three keyboard cases, at the real page.
    navigate(page, "shepherd")
    page.wait_for_selector("#shepherd-input")
    sends: list[str] = []
    page.on("request", lambda r: sends.append(r.url) if "/api/master/send" in r.url else None)
    page.click("#shepherd-input")
    page.keyboard.press("Enter")
    assert sends == [], "an empty composer must be a no-op"
    page.fill("#shepherd-input", "line one")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("line two")
    assert "\n" in page.input_value("#shepherd-input"), page.input_value("#shepherd-input")
    assert sends == [], "Shift+Enter must newline, not send"
    page.keyboard.press("Enter")
    await_true(lambda: len(sends) == 1, f"Enter did not send: {sends}")

    console.assert_clean("S28:")
    window = harness.rig.control("S28", since=mark)
    window.assert_kinds(["project.created"], prefix="project.")

    client.delete_project(str(rows[0]["project_id"]))
    harness.report.record(
        "S28",
        "ui",
        "PASS",
        "two Create clicks in one tick produce ONE POST, ONE workspace row and ONE "
        "frame; the composer's three keyboard cases behave (Enter sends, "
        "Shift+Enter newlines, empty is a no-op)",
        f"create_posts={len(creates)}; rows={len(rows)}; master_sends={len(sends)}",
        declared_uncovered=(
            "Four other POST handlers are deliberately unguarded on an "
            "idempotency bet. Driving them would assert the bet, not the guard."
        ),
    )


def test_s33_the_pages_validation_surface(harness: Harness) -> None:
    """S33 — four of the nine named values, and the duplicate-name re-arm chain.

    Two dialog modes, because the controls live in different ones
    (`projects.js:549`): `#p-new-path` is hidden outside edit mode and
    `addDraftPath` returns at `:586` before any request is built.
    """
    client, store, seeded = harness.client, harness.store, harness.seeded
    p1 = seeded.project("P1")
    workspaces_before = len(client.projects())
    edges_before = store.repo_counts().get(p1)
    mark = harness.rig.open_window()

    page, console = harness.open(nav="projects", width=DESKTOP, label="S33")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(f"{r.method} {r.url}") if r.method == "POST" else None)

    page.wait_for_selector("#proj-new")

    # ----- create mode -----------------------------------------------------
    page.click("#proj-new")
    page.wait_for_function("() => document.getElementById('dlg-project').open === true")

    static = REPO / "src" / "shepherd" / "web" / "static"
    module = (static / "projects.js").read_text(encoding="utf-8")
    needs_name = re.search(r'NEEDS_NAME\s*=\s*"([^"]+)"', module)
    assert needs_name is not None, "no NEEDS_NAME constant in projects.js"
    NEEDS_NAME = needs_name.group(1)

    def duplicate_warning(name: str) -> str:
        """`duplicateWarning`'s text, assembled from the module's own two
        fragments rather than re-spelled here."""
        match = re.search(
            r'There is already a project named "\$\{name\}"\.([^`]*)`\s*\+\s*\n?\s*"([^"]+)"',
            module,
        )
        assert match is not None, "no duplicateWarning template in projects.js"
        return f'There is already a project named "{name}".{match.group(1)}{match.group(2)}'

    def press_save(expect: str | None) -> str:
        """Press Create and read the refusal.

        **`submitProject` is `async`, so the refusal is written a microtask
        later.** `page.click` returns once the event has been dispatched, and a
        read taken on the next line sometimes ran *before* `showRefusal` — a
        race that failed this scenario about one run in two, always on a
        healthy page. A flaky test is a broken test, so the read is a bounded
        wait on the **exact** expected sentence rather than on "non-empty": the
        five presses expect "", NEEDS_NAME, dup("Shepherd"), dup("Flock"),
        dup("Shepherd") in that order, so no two consecutive expectations are
        equal and an equality wait cannot be satisfied by the previous press's
        text. The one press whose expectation IS the prior state — (a)'s empty
        string — is asserted through `validity.valueMissing` and a POST count
        instead, which is where its real content lies.
        """
        page.click("#p-save")
        if expect:
            try:
                page.wait_for_function(
                    "(args) => document.querySelector(args.selector).textContent.trim()"
                    " === args.expected",
                    arg={"selector": "#p-refusal", "expected": expect},
                )
            except Exception as error:  # noqa: BLE001 - re-raised with the measurement
                state = page.evaluate(
                    "() => ({refusal: document.getElementById('p-refusal').textContent,"
                    " name: document.getElementById('p-name').value,"
                    " open: document.getElementById('dlg-project').open,"
                    " valid: document.getElementById('p-name').validity.valid})"
                )
                raise AssertionError(
                    f"#p-refusal never reached the expected sentence.\n"
                    f"  expected: {expect!r}\n  page state: {state!r}\n  ({error})"
                ) from None
        return page.eval_on_selector("#p-refusal", "el => el.textContent.trim()")

    def attempt(name: str, expect: str | None = None) -> str:
        page.fill("#p-name", name)
        text = press_save(expect)
        if expect is not None:
            assert text == expect, f"expected {expect!r} in #p-refusal, got {text!r}"
        return text

    # **(a) an EMPTY name never reaches the page at all.** `#p-name` carries
    # `required` and `#p-save` is the form's submit control, so the browser's
    # own constraint validation blocks the submission: `submitProject` does not
    # run, `#p-refusal` stays empty, and what a person sees is the browser's
    # native tooltip. The plan's row asks for `NEEDS_NAME` here; measured,
    # `NEEDS_NAME` is **(b)'s** sentence — which is exactly what
    # `projects.js:658-660`'s own comment says: *"`required` is satisfied by a
    # space, so the browser submits and this used to `return` with nothing said
    # at all."* Both halves are asserted at their real seams and the divergence
    # is reported, rather than the row being weakened to "something is refused".
    empty_refusal = attempt("", "")
    assert posts == [], f"an empty name issues nothing: {posts}"
    assert page.eval_on_selector("#p-name", "el => el.validity.valueMissing") is True, (
        "the browser's own `required` is what refuses an empty name"
    )

    # (b) a single space **is** accepted by `required`, reaches the handler, and
    # must not be trimmed to "" and returned from with nothing said.
    space_refusal = attempt(" ", NEEDS_NAME)
    assert posts == [], f"a single space is the page's branch, and issues nothing: {posts}"

    # (c) the duplicate-name warn / re-arm chain, **without closing the dialog**
    # (`:547` resets `duplicate.armed` on every open, which is page behaviour
    # and not a re-arm; conflating the two makes this pass for the wrong reason).
    #
    # **The intermediate name must itself be a duplicate.** `duplicate.armed` is
    # set only on a *warned* press (`:666-667`) and cleared only on a successful
    # create (`:674`), so typing a different name changes nothing on its own and
    # pressing Create on a *unique* name creates that project and closes the
    # dialog. The round trip is therefore driven through a second existing name,
    # "Flock", which warns in its own right and moves the arm off "Shepherd" —
    # after which "Shepherd" warns again. That is the per-name property the plan
    # is after; its literal sequence, with the intermediate name never pressed,
    # cannot re-arm on this tree.
    first_warn = attempt("Shepherd", duplicate_warning("Shepherd"))
    assert posts == [], f"the warning must not create: {posts}"

    flock_warn = attempt("Flock", duplicate_warning("Flock"))
    assert posts == [], f"the arm is per-name, so a second duplicate warns too: {posts}"

    second_warn = attempt("Shepherd", duplicate_warning("Shepherd"))
    assert second_warn == first_warn, (first_warn, second_warn)
    assert posts == [], f"a re-armed warning must not create: {posts}"

    page.click("#p-save")
    page.wait_for_function("() => document.getElementById('dlg-project').open === false")
    creates = [item for item in posts if item.rstrip("/").endswith("/api/projects")]
    assert len(creates) == 1, f"exactly the fourth press creates: {posts}"

    # ----- edit mode -------------------------------------------------------
    page.click(f"#proj-list .proj-row[data-project-id='{p1}']")
    # **Wait for the DETAIL to be P1's**, not merely for `#proj-edit` to exist.
    # (c)'s fourth press creates a project and `submitProject` drills the detail
    # pane onto it, so `#proj-edit` is already on screen — belonging to the new
    # project. Clicking it there opens the edit dialog on a workspace with zero
    # repos, and the draft list never reaches two.
    # **Wait for P1's own DATA to be in the detail pane.** Two nearer-looking
    # signals are both races: `#proj-edit` already exists, belonging to the
    # project (c)'s fourth press created and drilled to; and `aria-current` is
    # set by `renderList()`, which the row's click handler calls **without
    # awaiting `loadDetail`** (`projects.js:250-254`), so it flips a frame
    # before the pane's contents do. P1's first repo path appears in no other
    # project, so its presence is the arrival signal.
    # **Settle the page before opening the edit dialog.**
    # `projectRow`'s click handler calls `loadDetail(id)` **without awaiting it**
    # and then `renderList()` (`projects.js:250-254`), and `submitProject`'s
    # create branch has already started a `loadDetail` of its own. Two unawaited
    # reads are in flight, and the later one to *resolve* wins — so the detail
    # pane can show P1 for a frame and then be overwritten, leaving `#proj-edit`
    # bound to a different project and the draft list stuck at zero. That is a
    # real race and it produced a flake at about one full-suite run in four.
    # `networkidle` is a sound settle **on this page specifically**: §12 forbids
    # polling and the product runs no timers, so "no requests in flight" is a
    # stable state rather than a momentary gap between ticks.
    #
    # **And the defect is DECLARED, not absorbed.** A shipped race that exists in
    # the deliverable only as this comment has been reported to nobody; a settle
    # in the harness is not a fix in the product.
    harness.report.declare(LOAD_DETAIL_RACE_DECLARATION)
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "(path) => { const el = document.getElementById('proj-detail');"
        " return el !== null && el.innerText.includes(path); }",
        arg=str(seeded.paths["P1_FIRST"]),
    )
    presses = press_until_open(
        page, "dlg-project", lambda: page.click("#proj-edit"), "S33 edit dialog"
    )
    harness.report.measure("s33_edit_dialog_presses", presses)
    assert page.eval_on_selector("#p-paths-section", "el => el.hidden") is False
    page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 2")

    refusals: dict[str, str] = {}
    for label, value in (
        ("missing", str(harness.run.sub("work") / "no-such-path-for-s33")),
        ("non-directory", str(seeded.paths["R3"])),
    ):
        adds_before = len([item for item in posts if "/repos/add" in item])
        page.fill("#p-new-path", value)
        page.click("#p-add-path")
        await_true(
            lambda: len([item for item in posts if "/repos/add" in item]) == adds_before + 1,
            f"{label}: exactly one …/repos/add must be issued",
        )
        # **Wait for the refusal to name THIS path**, not merely to be
        # non-empty: the previous leg's refusal is still on screen, so a
        # non-empty wait passes instantly on the wrong sentence. The assertion
        # below would still catch it — the two paths have different basenames —
        # but it would catch it as a flake rather than as a wait.
        page.wait_for_function(
            "(needle) => document.getElementById('p-refusal').textContent.includes(needle)",
            arg=value.split("/")[-1],
        )
        refusals[label] = page.eval_on_selector("#p-refusal", "el => el.textContent.trim()")
        assert value.split("/")[-1] in refusals[label] or value in refusals[label], (
            f"{label}: the refusal must name the path — {refusals[label]!r}"
        )
        assert page.eval_on_selector_all("#p-paths .path", "els => els.length") == 2, (
            f"{label}: the draft list must still show P1's two existing repos"
        )

    page.eval_on_selector("#dlg-project", "el => el.close()")
    console.assert_clean("S33:")

    window = harness.rig.control("S33", since=mark)
    window.assert_kinds(["project.created"], prefix="project.")

    # Surviving-row counts are read **after** the control and are net of it.
    after = client.projects()
    assert len(after) == workspaces_before + 1, [row.get("name") for row in after]
    assert store.repo_counts().get(p1) == edges_before, "no new workspace_repo edge"

    created = [row for row in after if row.get("name") == "Shepherd"]
    assert len(created) == 3, [row.get("name") for row in after]
    newest = max(created, key=lambda row: str(row["project_id"]))
    client.delete_project(str(newest["project_id"]))

    harness.report.record(
        "S33",
        "ui",
        "PASS",
        "(a) issues EXACTLY ZERO requests and is refused by `required` itself; "
        "(b) issues EXACTLY ZERO requests and renders NEEDS_NAME in #p-refusal; "
        "(c) warns, warns again on a second duplicate, re-arms and warns on the "
        "first name again, then creates on the fourth press — one workspace; (d),(e) each issue exactly one "
        "…/repos/add answering added==false with a refusal naming the path, and "
        "P1's two existing draft paths are unchanged; exactly one new workspace "
        "row net of the control; no new edge",
        f"empty: #p-refusal={empty_refusal!r} with validity.valueMissing=True; "
        f"space: {space_refusal[:60]!r}; warnings={first_warn[:44]!r} / "
        f"{flock_warn[:44]!r} / {second_warn[:44]!r}; "
        f"path refusals={ {k: v[:90] for k, v in refusals.items()} }; posts={posts}",
        measurement=(
            "(a) an empty name is refused by the browser's own `required`, not by "
            "the page: submitProject never runs and #p-refusal stays empty. "
            "NEEDS_NAME is (b)'s sentence. (c) re-arms only through a second "
            "*duplicate* name — duplicate.armed is set on a warned press and "
            "cleared on a successful create, so typing a name and typing it back "
            "does not re-arm."
        ),
    )


def test_s34_the_wires_refusal_surface(harness: Harness) -> None:
    """S34 — three `GENERIC_ERROR` statuses, the origin check on POST, the
    dropped-undeclared-field rule, and `add_repo`'s refusal over R2."""
    client, store, seeded = harness.client, harness.store, harness.seeded
    p1 = seeded.project("P1")
    original_name = store.get_workspace(p1).name  # type: ignore[union-attr]
    edges_before = store.repo_counts().get(p1)

    # The decoy this scenario owns. Its `project.created` frame opens the window.
    # **The decoy's `project.created` frame opens the window**, so the mark for
    # it is taken *before* the POST and the frame is awaited before the counted
    # window starts. A mark taken the instant the POST returns races the reader
    # thread, and the decoy's own frame then lands inside the window it was
    # supposed to open.
    opening = harness.rig.open_window()
    decoy = client.create_project("S34-DECOY")
    decoy_id = str(decoy["project"]["project_id"])  # type: ignore[index]
    decoy_name = str(decoy["project"]["name"])  # type: ignore[index]
    for name in ("A", "B"):
        harness.rig.await_kind(opening, "project.created", name)
    mark = harness.rig.open_window()
    audit_mark = harness.audit.mark()

    # (a) a cross-origin POST. The refusal happens **before the body is read**
    # (`server.py:192-193`, ahead of `_json_body`).
    evil = client.request(
        "POST",
        "/api/projects",
        body=json.dumps({"name": "S34-should-never-exist"}),
        headers={
            "Host": client.host,
            "Origin": "http://evil.example",
            "Content-Type": "application/json",
        },
    )
    correlation_a = assert_generic_error(evil, 403)

    # (b) a body that is not JSON.
    garbage = client.request(
        "POST",
        "/api/projects",
        body="this is not json",
        headers={"Host": client.host, "Origin": client.origin, "Content-Type": "application/json"},
    )
    correlation_b = assert_generic_error(garbage, 400)

    # (c) a path no template matches.
    nowhere = client.post("/api/projects/no-such-template/nowhere", {})
    correlation_c = assert_generic_error(nowhere, 404)

    # (d) one declared field, one named exactly as the path parameter, one
    # undeclared. **`project_id`, not `workspace_id`**: the latter is dropped by
    # the same undeclared-field rule as `colour` and so proves nothing about
    # redirection. What this proves is a conjunction of two guards the seam
    # cannot separate — `routes.py:247-249` drops it, and `:250` applies the
    # path parameter last — and the single-guard blindness is a declared gap.
    name_before = str(client.get(f"/api/projects/{decoy_id}").data()["project"]["name"])  # type: ignore[index]
    renamed = client.post(
        f"/api/projects/{p1}/rename",
        {"name": "S34-renamed", "project_id": decoy_id, "colour": "blue"},
    )
    assert renamed.status == 200, renamed.body
    assert renamed.data()["renamed"] is True, renamed.body
    name_after = str(client.get(f"/api/projects/{decoy_id}").data()["project"]["name"])  # type: ignore[index]
    assert name_before == name_after == decoy_name, (name_before, name_after, decoy_name)
    assert store.get_workspace(p1).name == "S34-renamed"  # type: ignore[union-attr]

    # (e) `add_repo` over R2 — a directory that is not a repository.
    refused = client.add_repo(p1, str(seeded.paths["R2"]))
    assert refused["added"] is False, refused
    assert isinstance(refused["refused"], str) and refused["refused"].strip(), refused
    assert store.repo_counts().get(p1) == edges_before, "a refused add must create no edge"

    # (a), (b) and (c) never reach the chokepoint, so they append nothing.
    tools = harness.audit.mutation_tools_since(audit_mark)
    assert tools == ["rename_project", "add_repo"], tools

    window = harness.rig.control("S34", since=mark)
    window.assert_kinds(["project.renamed"], prefix="project.")

    # Cleanup, and the decoy's own delete frame is asserted after the control.
    client.rename_project(p1, original_name)
    cleanup_mark = harness.rig.open_window()
    client.delete_project(decoy_id)
    harness.rig.await_kind(cleanup_mark, "project.deleted", "B")

    harness.report.record(
        "S34",
        "e2e_backend",
        "PASS",
        "(a) 403, (b) 400, (c) 404, each with exactly "
        '{"ok":false,"data":null,"error":"GENERIC_ERROR","correlation_id":"<32 hex>"} '
        "and the id matched as a pattern; (d) 200, the rename lands on P1 and the "
        "body's project_id redirects nothing while the undeclared colour is "
        "dropped; (e) added==false with a refusal naming the directory; exactly "
        "one project.renamed frame and none from the four refusals; audit records "
        "for (d) and (e) only",
        f"correlation ids={[correlation_a, correlation_b, correlation_c]}; "
        f"decoy name {name_before!r} -> {name_after!r}; audit={tools}",
        deferred_gap=(
            "This seam cannot separate routes.py's two no-redirect guards: "
            "removing either alone leaves the assertion green. The unit seam that "
            "can is tests/web/test_routes_m3.py::"
            "test_no_declared_field_shadows_a_path_parameter."
        ),
    )


def test_s30_the_ac28_substitute(harness: Harness) -> None:
    """S30 — a served render sweep over `render_check.VIEWPORTS`, **by
    reference**, carrying no `live` marker."""
    shots = harness.shots_dir() / "s30"
    shots.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        str(REPO / "tools" / "render_check.py"),
        "--url",
        f"{harness.client.origin}/",
        "--fail-on-empty",
        "--must-fill",
        # The screenshot directory is **positional** (`render_check.py:164-170`,
        # `rest`), not `--out`. Passing a flag the tool does not declare exits 2
        # on an argparse usage error, which looks exactly like a layout failure.
        str(shots),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=600, check=False)
    assert done.returncode == 0, (
        f"render_check exited {done.returncode}\nSTDOUT:\n{done.stdout[-4000:]}\n"
        f"STDERR:\n{done.stderr[-2000:]}"
    )
    assert "0 failures" in done.stdout, done.stdout
    # The sweep names its screenshots `<viewport>-<target>.png`
    # (`render_check.py:380`), so the **files** are where the viewport list is
    # observable — the summary line prints counts, not names. `VIEWPORTS` is
    # read from the module by reference; the number of page roots is derived
    # from what was written rather than spelled.
    written = sorted(path.name for path in shots.glob("*.png"))
    for name, width, height in VIEWPORTS:
        assert any(shot.startswith(f"{name}-") for shot in written), (
            f"the sweep wrote no screenshot for the {name} viewport "
            f"({width}x{height}): {written}"
        )
    roots = len(written) // len(VIEWPORTS)
    assert f"{len(VIEWPORTS) * roots} pages checked" in done.stdout, done.stdout

    harness.report.declare(AC28_DECLARATION)
    harness.report.record(
        "S30",
        "ui",
        "PASS",
        "render_check.py against the SERVED url with --fail-on-empty and "
        "--must-fill exits 0 over every entry of render_check.VIEWPORTS, read "
        "from the module and never re-spelled",
        f"argv={argv[1:]}; viewports={[name for name, _w, _h in VIEWPORTS]}; "
        f"exit={done.returncode}; summary={done.stdout.strip().splitlines()[-2:]}; "
        f"screenshots={len(written)} over {roots} page roots",
        declaration=AC28_DECLARATION,
        unfalsifiable_here=(
            "--fail-on-empty is a whole-body emptiness check and index.html ships "
            "the nav, the wordmark and the section labels as static markup, so the "
            "body can never be empty while the shell is served. It costs nothing "
            "and catches a server answering 200 with nothing; it is not evidence "
            "about layout. --must-fill is the flag that engages FILL_FLOOR."
        ),
    )


def test_s31_measure_the_tree_and_declare_the_stale_clauses(harness: Harness) -> None:
    """S31 — C-1 and C-3. Measurements and declarations; it amends nothing.

    A run that rewrites its own exam and then passes it is the exact failure
    this route exists to prevent.
    """
    sys.path.insert(0, str(REPO / "src"))
    from shepherd.web import routes

    manifest = json.loads((REPO / "tests" / "boundaries" / "consumer_manifest.json").read_text())
    measured = {
        "BODY_ARGS": len(routes.BODY_ARGS),
        "API_ROUTES": len(routes.API_ROUTES),
        "POST_ROUTES": len(routes.POST_ROUTES),
        "post_milestone.edits": len(manifest["post_milestone"]["edits"]),
    }

    def digest(relative: str) -> str:
        return hashlib.sha256((REPO / "src" / "shepherd" / relative).read_bytes()).hexdigest()

    server_digest = digest("web/server.py")
    terminal_digest = digest("web/static/terminal.js")
    baseline = manifest["baseline"]

    # **Compared against the manifest digest, never via `git diff`** — `git diff`
    # reads the working tree and asserts only "no uncommitted edits".
    assert server_digest == baseline["web/server.py"], (
        "web/server.py is byte-pinned and has moved: "
        f"{server_digest} != {baseline['web/server.py']}"
    )
    # **Subscript, never `.get`.** A dropped key makes `.get` answer `None`, the
    # comparison `False`, and `assert terminal_clean is False` pass — certifying
    # a divergence on the strength of no baseline at all. `web/server.py` four
    # lines above uses the subscript form; so does this.
    terminal_clean = terminal_digest == baseline["web/static/terminal.js"]

    stale = {
        "AC-16 says BODY_ARGS == 15": measured["BODY_ARGS"],
        "AC-21 says post_milestone.edits == 6": measured["post_milestone.edits"],
        "AC-23 assumes terminal.js is byte-clean": terminal_clean,
    }
    assert measured["BODY_ARGS"] == 16, measured
    assert measured["POST_ROUTES"] == 16, measured
    assert measured["API_ROUTES"] == 14, measured
    assert measured["post_milestone.edits"] == 7, measured
    assert terminal_clean is False, (
        "AC-23 assumes terminal.js matches its baseline digest; it now does, which "
        "is a different tree than the one this plan measured — report the change"
    )

    for text in (
        f"AC-16 is STALE: routes.BODY_ARGS is {measured['BODY_ARGS']}, not 15.",
        f"AC-21 is STALE: consumer_manifest post_milestone.edits is "
        f"{measured['post_milestone.edits']}, not 6.",
        "AC-23 is STALE: web/static/terminal.js no longer matches its manifest "
        "baseline digest, so the criterion's byte-clean assumption does not hold.",
    ):
        harness.report.declare(text)

    harness.report.measure("s31", {**measured, "server_sha256": server_digest,
                                   "terminal_sha256": terminal_digest})
    harness.report.record(
        "S31",
        "integration",
        "PASS",
        "BODY_ARGS == 16 (AC-16 says 15 — stale); post_milestone.edits == 7 "
        "(AC-21 says 6 — stale); terminal.js digest != its manifest baseline "
        "(AC-23 assumes byte-clean — stale); API_ROUTES == 14; POST_ROUTES == 16; "
        "sha256(web/server.py) equals the manifest baseline",
        f"{measured}; server_sha256={server_digest[:16]}…; "
        f"terminal_sha256={terminal_digest[:16]}…; stale={list(stale)}",
    )


#: Autonomy — the fourth Settings entry and the one built section carrying a
#: control that **writes** (`settings.js:351-357`). Named once.
BUILT_SECTION_INDEX = 3


def _await_text(page: Any, selector: str, expected: str, context: str) -> None:
    """Wait for an element to carry a string, and say what it carried if not.

    A bare `wait_for_function` that times out says only "timeout", which is the
    least useful thing a degradation test can say: the whole question is *which*
    sentence arrived. The actual text is read back and printed.
    """
    try:
        page.wait_for_function(
            "(args) => { const el = document.querySelector(args.selector);"
            " return el !== null && el.textContent.includes(args.expected); }",
            arg={"selector": selector, "expected": expected},
        )
    except Exception as error:  # noqa: BLE001 - re-raised with the measurement
        actual = page.eval_on_selector(
            selector, "el => el === null ? null : el.textContent"
        )
        raise AssertionError(
            f"{context}: {selector} never carried the module's own sentence.\n"
            f"  expected to contain: {expected!r}\n"
            f"  actual textContent:  {actual!r}\n"
            f"  ({error})"
        ) from None


def test_s29_the_daemon_dies_mid_flow(harness: Harness) -> None:
    """S29 — the degradation path, per module and per element. **Runs last.**

    Round 1 asserted that "each of the four modules writes *its own* unreachable
    sentence". Measured on this tree: `chat.js:131-132`, `app.js:65-66` and
    `projects.js:49-50` define the **byte-identical** string; only
    `settings.js:209-211` differs; and **`flock.js` has no `UNREACHABLE`
    constant at all** — the Flock's failure path runs through `app.js`'s own
    `read()` into the shell's shared banner. So this asserts the expected string
    in the expected element, one row per page, compared against the constant
    **read out of the module**, never re-spelled here.
    """
    static = REPO / "src" / "shepherd" / "web" / "static"

    def constant(module: str) -> str:
        text = (static / module).read_text(encoding="utf-8")
        match = re.search(r"UNREACHABLE\s*=\s*\n?\s*\"([^\"]+)\"", text) or re.search(
            r"UNREACHABLE\s*=\s*\n?\s*\"([^\"]+)\"\s*\+\s*\n?\s*\"([^\"]+)\"", text
        )
        assert match is not None, f"no UNREACHABLE constant in {module}"
        return "".join(part for part in match.groups() if part)

    shell_text = constant("app.js")
    settings_text = constant("settings.js")
    assert constant("chat.js") == shell_text, "chat.js and app.js must define the same string"
    assert constant("projects.js") == shell_text, "projects.js and app.js must agree"
    assert settings_text != shell_text, "settings.js is the one that differs"
    assert "UNREACHABLE" not in (static / "flock.js").read_text(encoding="utf-8"), (
        "flock.js has no unreachable sentence of its own — that absence is the "
        "product finding this scenario exists to be able to produce"
    )

    page, console = harness.open(nav="projects", width=DESKTOP, label="S29")
    for target in ("shepherd", "flock", "settings"):
        navigate(page, target)
    navigate(page, "projects")

    # --- the daemon dies ---------------------------------------------------
    outcome = __import__(
        "shepherd.daemons.controld", fromlist=["stop"]
    ).stop(harness.started)
    harness.controld_stopped = True
    assert outcome.hung == (), f"shutdown reported hung threads: {outcome.hung}"
    assert not harness.started.control_socket_path.exists()

    observed: dict[str, str] = {}
    rows = (
        ("shepherd", "#shepherd-status", shell_text),
        ("projects", "#p-refusal", shell_text),
        ("settings", "#settings-note", settings_text),
    )
    for target, selector, expected in rows:
        navigate(page, target)
        if target == "projects":
            page.click("#proj-new")
            page.fill("#p-name", "S29-unreachable")
            page.click("#p-save")
        elif target == "shepherd":
            page.fill("#shepherd-input", "anyone there")
            page.keyboard.press("Enter")
        elif target == "settings":
            # **Settings is deliberately not a live page**: `loadSettings()`
            # runs once at first paint and `onSettingsEvent` re-reads nothing —
            # "that would be polling driven by the stream, which is the same
            # defect wearing a different hat" (`settings.js:443-446`). So
            # navigating here after the daemon died issues no request at all and
            # `#settings-note` stays empty. The *action* the scenario calls for
            # is the one control on the page that writes: the Autonomy picker.
            page.locator("#settings-nav .set-item").nth(BUILT_SECTION_INDEX).click()
            page.wait_for_selector("#settings-panel .opt")
            page.locator("#settings-panel .opt").nth(0).click()
        _await_text(page, selector, expected, f"S29 {target}")
        observed[target] = page.eval_on_selector(selector, "el => el.textContent.trim()")
        # A dialog left open is a modal: it intercepts every pointer event on
        # the page behind it, so the next navigation would time out against a
        # control that is genuinely unreachable.
        page.evaluate(
            "() => { for (const d of document.querySelectorAll('dialog[open]')) d.close(); }"
        )

    # Flock: the shell's shared banner, unhidden — and **not** a spinner that
    # never resolves.
    #
    # **Navigating to the Flock issues no request.** `showPage` only reveals a
    # root; the shell re-reads on an *envelope*, and with the daemon down there
    # are none. The action that reaches `app.js`'s own `read()` is opening a
    # session — `openSession` fetches `/api/sessions/{id}` (`app.js:151-153`)
    # and its `catch` is what calls `showError(UNREACHABLE)` into the shared
    # banner. The cards are still on screen from the last successful read,
    # which is exactly the stale state this scenario is about.
    navigate(page, "flock")
    p1 = harness.seeded.project("P1")
    page.click(f"#flock-projects [data-project-id='{p1}']")
    page.wait_for_selector("[data-session-id]")
    page.click("[data-session-id] >> nth=0")
    page.wait_for_function(
        "(expected) => { const el = document.getElementById('stream-message-text');"
        " const box = document.getElementById('stream-message');"
        " return el !== null && el.textContent.includes(expected)"
        " && box.hidden === false; }",
        arg=shell_text,
    )
    observed["flock"] = page.eval_on_selector("#stream-message-text", "el => el.textContent.trim()")
    # `sse.js:33-35` sets `reconnecting` from the `EventSource` **error** event,
    # which the browser raises when it notices the socket is gone — not at the
    # instant the server stops. A bare read the moment after `controld.stop`
    # sees the last good value, so the wait is bounded and the failure is loud.
    # `sse.js:33-35` writes `reconnecting` from the `EventSource` **error**
    # event, which the browser raises when it notices the socket is gone — not
    # at the instant the server stops. **No source states how fast the page must
    # notice**, so this bound is a harness liveness bound and blowing it is a
    # measurement, never a product `FAIL` (§0 rule 1). It is reported either
    # way, and the scenario is `PARTIAL` rather than `PASS` when the assertion
    # could not be evaluated — a named assertion left unevaluated never rounds
    # up to a pass.
    noticed = True
    try:
        await_true(
            lambda: page.inner_text("#stream-status").strip().lower() != "live",
            "#stream-status",
            STREAM_NOTICE_CEILING_S,
        )
    except HarnessBlocked:
        noticed = False
    status = page.inner_text("#stream-status").strip().lower()
    if noticed:
        assert status in {"reconnecting", "unreadable"}, status

    # **`allow_network=True` here and nowhere else.** The property is that a
    # network failure is *handled* rather than thrown — no page `console.error`
    # and no `pageerror`. Chromium additionally logs
    # `Failed to load resource: net::ERR_CONNECTION_REFUSED` from the network
    # stack for every refused fetch, which correct handling cannot suppress;
    # asserting on it would make this scenario unpassable by construction. The
    # number seen is carried into the report rather than dropped.
    network_notices = [
        item for item in console.messages if Console.NETWORK_NOISE in item
    ]
    console.assert_clean("S29:", allow_network=True)

    if not noticed:
        harness.report.lose(
            "S29 PARTIAL: `#stream-status` still read `live` "
            f"{STREAM_NOTICE_CEILING_S:.0f}s after `controld.stop`. The banner and "
            "all three per-module sentences were evaluated and hold; this one "
            "named assertion was not evaluated. MEASUREMENT, not a FAIL: no "
            "source states how fast the page must notice a dropped stream, and "
            "an in-process shutdown may hold the socket open longer than a "
            "process exit would. Worth a product look: a page claiming `live` "
            "over a dead stream is the one state the indicator exists to deny."
        )

    harness.report.declare(
        "PRODUCT QUESTION, measured not invented: flock.js has no UNREACHABLE "
        "constant of its own. Its failure path runs through app.js's read() into "
        "the shell's shared banner (#stream-message-text). Whether one shell "
        "banner is correct for the one page whose read path IS the shell's, or a "
        "gap beside three modules that say it themselves, is a product decision."
    )
    harness.report.record(
        "S29",
        "ui",
        "PASS" if noticed else "PARTIAL",
        "with controld stopped: #shepherd-status and #p-refusal carry app.js's "
        "string, #settings-note carries settings.js's different one, and the "
        "Flock's failure surfaces in the shell's shared banner, unhidden, with "
        "#stream-status not reading live; every string compared against the "
        "constant read out of the module; zero console.error/pageerror — a "
        "network failure must be handled, not thrown",
        f"observed={ {k: v[:80] for k, v in observed.items()} }; "
        f"stream_status={status!r} (noticed={noticed}); "
        f"shutdown_hung={outcome.hung}; "
        f"browser network notices (not page errors)={len(network_notices)}",
    )
