"""Wave 1 — the pipeline is wired end to end, and C-6 is bound by measurement.

S0 is first not because it is cheap but because ten scenarios are uninterpretable
without it. Two authority documents describe `DeletePlan` differently; the delete
dialog's five choices, one of them disabled up front, rest on the answer. It is
settled empirically rather than by picking the likelier document.
"""

from __future__ import annotations

import re

import pytest

from .conftest import Harness
from .constants import DESKTOP, NAV_PAGES
from .dom import assert_one_root_visible
from .report import Evidence

DELETE_KEYS = ("running", "killable", "unkillable", "doomed", "kill_failures")


def test_s0_environment_truth_probe(harness: Harness) -> None:
    """S0 — the refusal record, measured; `KILLABLE` bound for waves 3 and 5.

    The expected binding is **B-OWNED**. `store/reads.py:283-284` is
    `killable = tuple(s.id for s in alive if s.runner_handle is not None)` and
    `tools_projects_delete.py:128-136` emits the three keys unconditionally, so
    with S-own-1 holding a handle and S-att-1 holding none the binding *follows
    from the seed*. This is a measurement that confirms a reading, not a gate
    choosing between four live possibilities — but the projection is what five
    scenarios consume, and reading it once beats inferring it four times.
    """
    seeded, client, store = harness.seeded, harness.client, harness.store
    p4 = seeded.project("P4")

    before = store.list_anomaly_counts().get("stop_failed", 0)
    audit_mark = harness.audit.mark()

    # No `on_running`, so the handler's default-refuse applies (D61).
    answer = client.delete_project(p4)

    assert answer["deleted"] is False, answer
    refused = answer["refused"]
    assert isinstance(refused, str) and refused.strip(), answer
    for key in DELETE_KEYS:
        assert key in answer, f"{key!r} must be emitted unconditionally: {sorted(answer)}"

    killable = list(answer["killable"])  # type: ignore[arg-type]
    unkillable = list(answer["unkillable"])  # type: ignore[arg-type]
    doomed = list(answer["doomed"])  # type: ignore[arg-type]
    running = list(answer["running"])  # type: ignore[arg-type]
    harness.bindings |= {
        "KILLABLE": killable,
        "UNKILLABLE": unkillable,
        "DOOMED": doomed,
        "RUNNING": running,
    }
    for name, value in harness.bindings.items():
        harness.report.bind(name, value)

    # --- the branch table, at its real weights ---------------------------
    own1, att1 = seeded.session("S-own-1"), seeded.session("S-att-1")
    binding = (
        "B-OWNED"
        if killable == [own1] and unkillable == [att1]
        else "B-EMPTY"
        if killable == [] and running
        else "B-ALL"
        if sorted(killable) == sorted(running)
        else "B-OTHER"
    )
    harness.bindings["S0_BINDING"] = binding
    harness.report.bind("S0_BINDING", binding)
    assert binding == "B-OWNED", (
        f"S0 bound {binding}, not B-OWNED. killable={killable} unkillable={unkillable} "
        f"running={running}. B-ALL and B-ABSENT are unreachable on this tree "
        "(reads.py:283-284, tools_projects_delete.py:128-136), so a departure is "
        "itself the finding and wave 1 stops on it."
    )

    # --- DB: the refusal changed nothing --------------------------------
    assert store.get_workspace(p4) is not None, "P4 must survive a refusal"
    alive = store.running_sessions_for(p4)
    assert {row.id for row in alive} == {own1, att1}, [row.id for row in alive]
    assert store.list_anomaly_counts().get("stop_failed", 0) == before, (
        "a refusal that killed nothing must not increment stop_failed"
    )
    assert len(doomed) == 5, f"P4 holds 2 running + 3 finished; doomed was {doomed}"

    # --- Logs: one audit record for the gated invoke --------------------
    records = harness.audit.since(audit_mark)
    delete_records = [row for row in records if row.get("tool") == "delete_project"]
    assert len(delete_records) == 1, [row.get("tool") for row in records]
    assert delete_records[0].get("decision") == "allow", delete_records[0]
    assert delete_records[0].get("approved_by") == "claimed_human", delete_records[0]

    # --- Queue: zero, and the control is what makes the zero mean anything
    window = harness.rig.control("S0")
    window.assert_empty("a refusal announces nothing")

    harness.report.record(
        "S0",
        "e2e_backend",
        "PASS",
        "200; deleted=false; a non-empty refusal; five projection keys; "
        "KILLABLE==[S-own-1], UNKILLABLE==[S-att-1]; P4 intact; no stop_failed; "
        "one allow/claimed_human audit record; zero frames in the window",
        f"binding={binding} killable={killable} unkillable={unkillable} "
        f"doomed={len(doomed)} running={running} refused={refused!r}",
        killable=killable,
        unkillable=unkillable,
        doomed=doomed,
        running=running,
    )


def test_s1_the_shell_is_served_and_every_root_mounts(harness: Harness) -> None:
    """S1 — six roots mount, exactly one is visible at a time, nothing errors."""
    page, console = harness.open(width=DESKTOP, label="S1")
    seen: list[str] = []
    assert_one_root_visible(page, "S1 at arrival:")

    for nav in NAV_PAGES:
        harness.nav(page, nav)
        visible = assert_one_root_visible(page, f"S1 after nav to {nav}:")
        assert visible == f"page-{nav}", f"nav to {nav} showed {visible}"
        current = page.eval_on_selector_all(
            ".nav-item[aria-current='page']", "els => els.map(e => e.dataset.page)"
        )
        assert current == [nav], f"aria-current is {current} after navigating to {nav}"
        seen.append(visible)

    # Queues and Kanban are static "not built this milestone" stubs with no
    # module. The assertion is that they render *and* produce no module error —
    # the second half is the one that would catch a stub that 404s its script.
    for stub in ("queues", "kanban"):
        harness.nav(page, stub)
        text = page.inner_text(f"#page-{stub}")
        assert text.strip(), f"#page-{stub} rendered nothing at all"

    console.assert_clean("S1:")
    harness.report.record(
        "S1",
        "ui",
        "PASS",
        "exactly one [id^=page-] visible at arrival and after every nav click; "
        "aria-current follows; the two stubs render; zero console.error/pageerror",
        f"roots seen in order: {seen}",
    )


def test_s2_the_reads_reflect_an_n_gt_1_world(harness: Harness) -> None:
    """S2 — eight workspaces, two sharing a name, and `unassigned` reserved."""
    client, store, seeded = harness.client, harness.store, harness.seeded
    rows = client.projects()
    assert len(rows) == 8, [row.get("name") for row in rows]

    by_id = {str(row["project_id"]): row for row in rows}
    assert "unassigned" in by_id

    shepherds = [row for row in rows if row.get("name") == "Shepherd"]
    assert len({str(row["project_id"]) for row in shepherds}) == 2, shepherds

    # `repo_count` on the **read** path. The write verbs answer 0
    # unconditionally (X3) and S6 asserts that divergence at the write seam;
    # neither is re-proved by the other.
    assert by_id[seeded.project("P1")]["repo_count"] == 2, by_id[seeded.project("P1")]
    assert by_id[seeded.project("P3")]["repo_count"] == 1, by_id[seeded.project("P3")]

    # C-7: `last_activity_at` is derived at read time. Never assert the column.
    for label in ("P1", "P4", "P5", "P6"):
        row = by_id[seeded.project(label)]
        assert row["last_activity_at"] is not None, f"{label} has sessions: {row}"

    detail = client.get(f"/api/projects/{seeded.project('P3')}").data()
    repos = client.get(f"/api/projects/{seeded.project('P3')}/repos").data()
    listed = repos.get("repos")
    assert isinstance(listed, list) and len(listed) == 1, repos
    assert str(seeded.paths["DEEP"]) in str(listed[0]), listed[0]

    # --- UI: eight rows, and the reserved row's controls are ABSENT --------
    page, console = harness.open(nav="projects", width=DESKTOP, label="S2")
    page.wait_for_selector("#proj-list .proj-row")
    count = page.eval_on_selector_all("#proj-list .proj-row", "els => els.length")
    assert count == 8, f"#proj-list showed {count} rows"

    reserved = "#proj-list .proj-row[data-project-id='unassigned']"
    page.wait_for_selector(reserved)
    for control in ("#proj-edit", "#proj-delete"):
        present = page.eval_on_selector_all(
            f"{reserved} {control}", "els => els.length"
        )
        assert present == 0, (
            f"the reserved row must have NO {control} child — absence, not disabled"
        )

    # The empty class: P2 has zero repos and zero sessions and must render the
    # module's own sentence, not a blank pane and not a spinner.
    page.click(f"#proj-list .proj-row[data-project-id='{seeded.project('P2')}']")
    page.wait_for_function(
        "() => document.getElementById('proj-detail').innerText.trim().length > 0"
    )
    empty_text = page.inner_text("#proj-detail").strip()
    assert empty_text, "#proj-detail is blank for a project with nothing in it"
    console.assert_clean("S2:")

    harness.report.record(
        "S2",
        "integration",
        "PASS",
        "eight workspaces; two ids share 'Shepherd'; read-path repo_count 2 and 1; "
        "last_activity_at derived; #proj-list eight rows; unassigned has no "
        "#proj-edit and no #proj-delete child; the empty class renders a sentence",
        f"names={[row.get('name') for row in rows]}; detail_keys={sorted(detail)}; "
        f"empty_pane={empty_text[:120]!r}",
    )


def test_s3_the_stream_opens_and_a_second_client_is_real(harness: Harness) -> None:
    """S3 — the rig's **contract** at the scenario seam, not the rig itself.

    Round 1 made this scenario the rig's constructor, so everything that counted
    frames before it was counting against nothing. The clients are attached and
    first proved live at bring-up step 10 and owned by the session fixture to
    teardown; S3 asserts the properties of the stream.
    """
    client, rig = harness.client, harness.rig
    for name, subscriber in rig.subscribers.items():
        assert subscriber.headers.get("content-type", "").startswith("text/event-stream"), (
            f"client {name}: {subscriber.headers}"
        )
        assert subscriber.headers.get("cache-control") == "no-store", subscriber.headers
        assert subscriber.headers.get("x-content-type-options") == "nosniff", subscriber.headers
        assert ": open" in subscriber.comments, (
            f"client {name} never saw the `: open` comment — without it "
            "'no frame' and 'socket alive' are indistinguishable"
        )

    # Cell (ii): strictly positive and unbounded above, so it is self-controlling.
    mark = rig.open_window()
    created = client.create_project("S3-probe")
    project = created["project"]
    assert isinstance(project, dict)
    probe_id = str(project["project_id"])

    frames = {}
    for name in ("A", "B"):
        frame = rig.await_kind(mark, "project.created", name)
        assert frame.project_id == probe_id, frame
        assert not frame.has_event_name, (
            "the frame must carry no `event:` name — a named frame reaches only a "
            "listener registered for that exact name, so the page would silently "
            "drop every type it was not written to expect"
        )
        assert frame.raw_fields.get("id") == str(frame.seq), frame.raw_fields
        frames[name] = frame

    # The negative control on the same surface: the origin check runs on the
    # **stream**, not only on mutations, and round 1 drove it on the WebSocket alone.
    refused = client.request(
        "GET",
        "/api/events",
        headers={"Host": client.host, "Origin": "http://evil.example"},
    )
    assert refused.status == 403, refused.status
    assert "data:" not in refused.body, f"a refused stream must have no body: {refused.body!r}"

    # **Cleanup settles its own frames.** A delete whose frame has not yet been
    # read by the rig leaves that frame to land inside the *next* scenario's
    # counted window, where it reads as a product event this plan did not
    # expect. The scenario that produced a frame is the one that waits for it.
    cleanup_mark = harness.rig.open_window()
    client.delete_project(probe_id)
    for name in ("A", "B"):
        harness.rig.await_kind(cleanup_mark, "project.deleted", name)

    harness.report.record(
        "S3",
        "e2e_backend",
        "PASS",
        "both streams 200 text/event-stream + no-store + nosniff; `: open` seen; "
        "both clients get project.created with `id: <seq>` and no `event:` name; "
        "a wrong-Origin stream is 403 with no stream body",
        f"seqs={{'A': {frames['A'].seq}, 'B': {frames['B'].seq}}}; "
        f"refusal={refused.status}",
    )
