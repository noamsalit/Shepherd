"""Wave 3 — the delete family against **real** running sessions and a real pane.

Order inside the wave is fixed: **S9, S10, S12, S11, S13.** S11 destroys P4's
pane and S12 reads P5, so S12 must not wait behind it.

S11 is the first kill this project has ever driven against a real pane. §3c's
fixture-side controls ran at bring-up precisely so that a red here is
attributable: with them green, a red S11 is a product `FAIL`; with either red it
is `BLOCKED`, and the run learned about the seed rather than the shipped kill.
"""

from __future__ import annotations

import pytest

from .conftest import Harness
from . import tmuxctl
from .constants import DESKTOP, PANES
from .rig import CREATED, DELETED
from .wire import await_true


def _require_binding(harness: Harness) -> list[str]:
    """Wave 3's premise, read from S0's **measured** binding.

    A skip here is the pytest expression of `BLOCKED`, and it is conditional on
    a measurement, never on a switch. It is also **recorded** — a skipped test
    that reports as passed is a lie with good manners, so the loss reaches the
    run report rather than the terminal's dot.

    **And it now carries a BLOCKED verdict, not only a loss line.**
    `conftest.pytest_runtest_makereport` writes one row per skipped scenario, so
    a blocked wave 3 reads `BLOCKED: 5` instead of `BLOCKED: 0` with five
    scenarios missing from the array entirely — and `pytest_sessionfinish`
    refuses to publish the run as `qa5-latest.json` either way, because the
    record set is then not the planned one.
    """
    binding = harness.bindings.get("S0_BINDING")
    if binding != "B-OWNED":
        harness.report.lose(
            f"wave 3 BLOCKED: S0 bound {binding!r}, not B-OWNED. With §3c's handle "
            "control green that is a product finding (the projection lost a handle "
            "the store round-tripped); with it red the seed never landed."
        )
        pytest.skip(f"S0 bound {binding!r}; wave 3 is BLOCKED, not FAIL")
    killable = harness.bindings["KILLABLE"]
    assert isinstance(killable, list)
    return killable


def _open_delete_dialog(page, project_id: str) -> None:
    page.click(f"#proj-list .proj-row[data-project-id='{project_id}']")
    page.wait_for_selector("#proj-delete")
    page.click("#proj-delete")
    page.wait_for_function("() => document.getElementById('dlg-delete').open === true")


def test_s9_the_refusal_record_is_rendered(harness: Harness) -> None:
    """S9 — the dialog's identity/doomed/live panels, and GAP 1.

    **The five choices are never co-resident, and that is a measurement.** The
    plan's UI row asks that `#dlg-delete-choices` "holds all five choices". The
    group is built in two phases: opening renders **one** (`delete`), and the
    other three arrive only from the *server's own refusal*
    (`projects.js:940-1005`), replacing it; `#dlg-delete-cancel` is a fifth
    control and lives outside the group entirely. `Wait` cannot be pressed
    before the refusal exists, so the sequence below is the only one that
    reaches it. Both counts are asserted, and the divergence is reported.
    """
    _require_binding(harness)
    doomed = harness.bindings["DOOMED"]
    running = harness.bindings["RUNNING"]
    p4 = harness.seeded.project("P4")
    store = harness.store
    mark = harness.rig.open_window()

    page, console = harness.open(nav="projects", width=DESKTOP, label="S9")
    posts: list[str] = []
    page.on(
        "request",
        lambda request: posts.append(f"{request.method} {request.url}")
        if request.method == "POST"
        else None,
    )
    reads: list[str] = []
    page.on(
        "request",
        lambda request: reads.append(request.url)
        if "/api/sessions" in request.url
        else None,
    )

    _open_delete_dialog(page, p4)
    assert posts == [], f"opening the dialog must fire no POST; it fired {posts}"

    identity = page.inner_text("#dlg-delete-identity")
    assert p4 in identity, f"the dialog must name P4 by id as well as by name: {identity!r}"
    assert "Doomed" in page.inner_text("#dlg-delete-title"), page.inner_text("#dlg-delete-title")

    opened_choices = page.eval_on_selector_all(
        "#dlg-delete-choices .dlg-choice", "els => els.map(e => e.dataset.choice)"
    )
    assert opened_choices == ["delete"], opened_choices
    assert page.eval_on_selector("#p-refusal", "el => el.textContent.trim()") == "", (
        "#p-refusal must be present and empty before anything is pressed"
    )
    assert page.eval_on_selector("#p-refusal", "el => el.hidden") is True

    # GAP 1: the number in front of the destructive button is the *server's*.
    # Pressing `delete` is what produces the refusal that carries `doomed`.
    reads_before = len(reads)
    page.click("#dlg-delete-choices .dlg-choice[data-choice='delete']")
    page.wait_for_function(
        "(n) => document.querySelectorAll('#dlg-delete-choices .dlg-choice').length === n",
        arg=3,
    )
    assert len(posts) == 1, f"exactly one POST from the press; fired {posts}"

    doomed_rows = page.eval_on_selector_all(
        "#dlg-delete-doomed .dlg-row", "els => els.map(e => e.textContent)"
    )
    # The label row plus one row per id.
    rendered = [row for row in doomed_rows if row in doomed]
    assert len(rendered) == len(doomed), (
        f"#dlg-delete-doomed shows {len(rendered)} of the server's {len(doomed)} ids: "
        f"{doomed_rows}"
    )
    live_text = page.inner_text("#dlg-delete-live")
    for session_id in running:
        assert session_id in live_text, f"{session_id} missing from #dlg-delete-live"

    # A second `list-sessions` request would be the page re-deriving what the
    # refusal already carried — GAP 1's shape.
    assert len(reads) == reads_before, (
        f"the page issued {len(reads) - reads_before} extra /api/sessions read(s) to "
        "produce a number the refusal already carried"
    )

    after_refusal = page.eval_on_selector_all(
        "#dlg-delete-choices .dlg-choice", "els => els.map(e => e.dataset.choice)"
    )
    assert sorted(after_refusal) == ["cancel", "kill_sessions", "orphan"], after_refusal

    # `Wait — keep the project` closes and writes nothing.
    posts_before = len(posts)
    page.click("#dlg-delete-choices .dlg-choice[data-choice='cancel']")
    page.wait_for_function("() => document.getElementById('dlg-delete').open === false")
    assert len(posts) == posts_before, "Wait must fire no POST"
    assert store.get_workspace(p4) is not None, "Wait must not delete the project"

    # `#dlg-delete-cancel` is the other control, and it does the same thing.
    _open_delete_dialog(page, p4)
    posts_before = len(posts)
    page.click("#dlg-delete-cancel")
    page.wait_for_function("() => document.getElementById('dlg-delete').open === false")
    assert len(posts) == posts_before, "#dlg-delete-cancel must fire no POST"
    assert store.get_workspace(p4) is not None

    console.assert_clean("S9:")
    window = harness.rig.control("S9", since=mark)
    window.assert_kinds([], prefix="project.")

    harness.report.record(
        "S9",
        "ui",
        "PASS",
        "the dialog names P4 by name and id; #dlg-delete-doomed renders the "
        "server's own ids, one per id; #dlg-delete-live lists both running "
        "sessions; Wait and #dlg-delete-cancel each close, write nothing and fire "
        "no POST; no second /api/sessions read; zero frames in the window",
        f"choices at open={opened_choices}; after the refusal={sorted(after_refusal)}; "
        f"posts={posts}",
        measurement=(
            "S9's UI row asks for five co-resident choices in #dlg-delete-choices. "
            "The group is two-phase: one at open, three from the server's refusal "
            "(projects.js:940-1005), and #dlg-delete-cancel is outside the group. "
            "Five distinct controls exist; they are never simultaneous."
        ),
    )


def test_s10_stop_them_then_delete_is_disabled_exactly_when_it_cannot_work(
    harness: Harness,
) -> None:
    """S10 — PP-3, at the seam a person sees: disabled **before** any click."""
    _require_binding(harness)
    seeded = harness.seeded
    mark = harness.rig.open_window()
    page, console = harness.open(nav="projects", width=DESKTOP, label="S10")

    observed: dict[str, dict[str, object]] = {}
    for label in ("P4", "P5"):
        project_id = seeded.project(label)
        _open_delete_dialog(page, project_id)
        page.click("#dlg-delete-choices .dlg-choice[data-choice='delete']")
        page.wait_for_selector("#dlg-delete-choices .dlg-choice[data-choice='kill_sessions']")
        state = page.eval_on_selector(
            "#dlg-delete-choices .dlg-choice[data-choice='kill_sessions']",
            "el => ({disabled: el.disabled, text: el.textContent})",
        )
        answer = harness.client.delete_project(project_id)
        killable = list(answer["killable"])  # type: ignore[arg-type]
        assert state["disabled"] == (len(killable) == 0), (
            f"{label}: the choice's disabled state must match "
            f"answer.killable.length === 0 exactly; killable={killable}, state={state}"
        )
        observed[label] = {"disabled": state["disabled"], "killable": killable}
        page.click("#dlg-delete-cancel")
        page.wait_for_function("() => document.getElementById('dlg-delete').open === false")

    assert observed["P4"]["disabled"] is False, observed
    assert observed["P5"]["disabled"] is True, observed
    console.assert_clean("S10:")

    window = harness.rig.control("S10", since=mark)
    window.assert_kinds([], prefix="project.")
    harness.report.record(
        "S10",
        "ui",
        "PASS",
        "on P4 (killable non-empty) the kill_sessions choice is enabled; on P5 "
        "(attached-only) it is disabled, and the disabled state is visible before "
        "any click; both match answer.killable.length === 0 exactly; zero frames",
        f"{observed}",
    )


def test_s12_a_kill_that_cannot_land_says_why(harness: Harness) -> None:
    """S12 — GAP 2, over **P5**, whose entire subject was unprovisioned before."""
    _require_binding(harness)
    client, store, seeded = harness.client, harness.store, harness.seeded
    p5 = seeded.project("P5")
    before = store.list_anomaly_counts().get("stop_failed", 0)
    ended_before = {row.id: row.ended_at for row in store.running_sessions_for(p5)}
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    answer = client.delete_project(p5, on_running="kill_sessions")
    assert answer["deleted"] is False, answer
    assert answer["killed"] == [], answer

    # **`kill_failures` records a RAISE, not a `no_pane`.** The plan's row asks
    # for one failure per attached session "with a reason naming no_pane". That
    # is not this tree: `kill_for_delete` reads `kill_session_now`'s answer
    # through `kill_landed` and returns **False** for `no_pane`
    # (`compose.py:451-462`), and `_kill_running` only appends to `failures`
    # inside `except` (`tools_projects_delete.py:174-178`). A `no_pane` session
    # is therefore in neither list, and `stop_failed` does not move. S17 is the
    # scenario that produces a real raise, and its `RunnerRefusal:` prefix is
    # exactly `f"{type(refusal).__name__}: {refusal}"`. Reported as a
    # measurement (§0 rule 5), never as a product FAIL.
    failures = answer["kill_failures"]
    assert failures == [], (
        f"kill_failures records raises only; a no_pane answer is a False: {failures}"
    )
    running_after = list(answer["running"])  # type: ignore[arg-type]
    assert set(running_after) == set(ended_before), (running_after, ended_before)
    refused = answer["refused"]
    assert isinstance(refused, str) and refused.strip(), answer

    assert store.get_workspace(p5) is not None, "P5 must be kept"
    still = {row.id: row.ended_at for row in store.running_sessions_for(p5)}
    assert still == ended_before, (ended_before, still)
    after = store.list_anomaly_counts().get("stop_failed", 0)
    assert after == before, (
        f"no kill raised, so stop_failed must not move: {before} -> {after}"
    )

    # The UI half: the reader added for run-2 d1.
    page, console = harness.open(nav="projects", width=DESKTOP, label="S12")
    _open_delete_dialog(page, p5)
    page.click("#dlg-delete-choices .dlg-choice[data-choice='delete']")
    page.wait_for_selector("#dlg-delete-choices .dlg-choice[data-choice='kill_sessions']")
    # The kill choice is **disabled** here, which is S10's assertion and is
    # correct: P5's killable is empty. The refusal the plan asks this scenario
    # to read is the one the first press already produced, so there is nothing
    # to click — and clicking a disabled control to reach it would be asserting
    # that the guard S10 just proved does not hold.
    assert page.eval_on_selector(
        "#dlg-delete-choices .dlg-choice[data-choice='kill_sessions']", "el => el.disabled"
    ) is True
    page.wait_for_function(
        "() => document.getElementById('dlg-delete-live').innerText.includes('Still running')"
    )
    live_text = page.inner_text("#dlg-delete-live")
    for session_id in running_after:
        assert session_id in live_text, (session_id, live_text)
    # "…and why" is the server's own refusal sentence, written into the body by
    # `projects.js:970`. With no raise there is no `.dlg-reason` node, which is
    # the same measurement as the API row above — the reader added for run-2 d1
    # renders `kill_failures`, and `kill_failures` is empty for a no_pane.
    reasons = page.eval_on_selector_all(
        "#dlg-delete-live .dlg-reason", "els => els.map(e => e.textContent)"
    )
    assert reasons == [], reasons
    # The dialog's sentence is the **default-refuse** one: the first press
    # carries no `on_running` at all (`projects.js:724`), so the server answers
    # the "choose what happens to them" refusal rather than the kill_sessions
    # one the API leg above drove. Two different refusals, both correct; the
    # assertion is on the one this press actually produced.
    body = page.inner_text("#dlg-delete-body")
    assert f"{len(running_after)} session(s) are still running" in body, body
    assert "choose whether to stop them" in body, body
    page.click("#dlg-delete-cancel")
    console.assert_clean("S12:")

    assert harness.audit.mutation_tools_since(audit_mark).count("delete_project") == 2, (
        harness.audit.mutation_tools_since(audit_mark)
    )
    window = harness.rig.control("S12", since=mark)
    window.assert_kinds([], prefix="project.")

    harness.report.record(
        "S12",
        "e2e_backend",
        "PASS",
        "deleted=false; killed=[]; kill_failures==[] (a no_pane is a False, not a "
        "raise — see measurement); a non-empty refusal; P5 kept; no ended_at "
        "moved; stop_failed UNCHANGED; the kill choice is disabled and the "
        "dialog's live region names every still-running session id with no "
        ".dlg-reason node; the body carries the default-refuse sentence; exactly "
        "two delete_project audit records; zero project.* frames in the window",
        f"failures={failures}; running={running_after}; stop_failed {before}->{after}; "
        f"reasons={reasons}; body={body[:160]!r}",
        measurement=(
            "SUPERSEDED PLAN WORDING (test-plan S12, API and UI rows): 'deleted=false, "
            "killed=[], one kill_failure per attached session with a reason naming "
            "no_pane, a non-empty refusal; ... stop_failed up by exactly the failure "
            "count; the dialog renders what was not stopped and why, naming the "
            "session id'. That is what the plan asked for; the `expected` field "
            "above is what this scenario asserts, because the `expected` field is "
            "the one a reader scans and it must not state the opposite of the code. "
            "Why they differ: kill_failures records a "
            "RAISE only (tools_projects_delete.py:174-178); kill_for_delete turns "
            "no_pane into False (compose.py:451-462). The sessions appear under "
            "`running` and in '#dlg-delete-live' as 'Still running:', with the "
            "why carried by the refusal sentence in #dlg-delete-body. stop_failed "
            "does not move. A finding about the plan's reading, not a product FAIL."
        ),
    )


def test_s11_a_kill_that_lands_on_a_real_pane(harness: Harness) -> None:
    """S11 — PP-3 and PP-4. The never-driven kill chain, on a live pane."""
    killable = _require_binding(harness)
    client, store, seeded = harness.client, harness.store, harness.seeded
    p4, own1, att1 = seeded.project("P4"), seeded.session("S-own-1"), seeded.session("S-att-1")
    pane = PANES[0]

    assert pane in tmuxctl.sessions(), f"{pane} must be live before the kill"
    assert killable == [own1], killable
    before = store.list_anomaly_counts().get("stop_failed", 0)
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    answer = client.delete_project(p4, on_running="kill_sessions")

    assert list(answer["killed"]) == [own1], answer  # type: ignore[arg-type]
    # Same measurement as S12: an attached session's `no_pane` is a `False`,
    # not a raise, so it lands in neither `killed` nor `kill_failures`. It is
    # `running` that still names it, and `refused` that explains.
    failures = answer["kill_failures"]
    assert failures == [], failures
    assert att1 in list(answer["running"]), answer  # type: ignore[arg-type]
    # The refusal **counts** the survivors; it does not name them. The plan's
    # row says "refused names the surviving session"; measured, the sentence is
    # `store/projects.py`'s own "N session(s) in this project are still running
    # and were not stopped; nothing was deleted". The ids are carried by
    # `running`, which is where the dialog reads them from. Measurement.
    refused = answer["refused"]
    assert isinstance(refused, str) and refused.strip(), answer
    assert "still running" in refused, refused
    assert refused.startswith(f"{len(list(answer['running']))} session"), refused

    # --- tmux: the pane is gone from OUR socket. `-L` explicit. ----------
    await_true(lambda: pane not in tmuxctl.sessions(), f"{pane} was still listed after the kill")
    remaining = tmuxctl.sessions()
    assert pane not in remaining, remaining

    # **Pinned, not derived from the answer.** `expected = [...] if deleted else []`
    # reads the expectation off the value under test: whatever the product says,
    # the assertion agrees, and both branches print green. `deleted` is
    # deterministic on this tree — `commit_project_delete` re-derives the running
    # set inside its own transaction and refuses unconditionally while any row
    # remains (`store/projects.py:241-259`), and S-att-1 is attached, has no pane
    # and cannot be stopped. So the value is stated here, once, and a tree where
    # it changed goes red instead of quietly re-shaping the rest of the scenario.
    deleted = answer["deleted"]
    assert deleted is False, (
        "P4 still holds the unkillable S-att-1, so the re-derived running set is "
        f"non-empty and the delete must refuse: deleted={deleted}"
    )
    row = store.get_session(own1)
    assert row is not None and row.ended_at is not None, "the killed session must carry ended_at"
    other = store.get_session(att1)
    assert other is not None and other.ended_at is None, "the unkillable one must be untouched"
    assert (store.get_workspace(p4) is None) is bool(deleted), (
        f"the project's fate must match the API's deleted value exactly: deleted={deleted}"
    )
    after = store.list_anomaly_counts().get("stop_failed", 0)
    assert after == before, f"no kill raised, so stop_failed must not move: {before} -> {after}"

    records = harness.audit.records_for(audit_mark, "delete_project")
    assert len(records) == 1, records
    assert records[0].get("approved_by") == "claimed_human", records[0]

    window = harness.rig.control("S11", since=mark)
    expected = ["project.deleted"] if deleted else []
    window.assert_kinds(expected, prefix="project.")
    # The kill's own event is on the same ring, and a window read as a bare list
    # would have counted it. It is asserted here as evidence rather than filtered
    # away silently: a kill that landed and announced nothing would be a finding.
    session_frames = window.kinds(prefix="session.")
    assert session_frames == ["session.killed"], session_frames

    harness.report.record(
        "S11",
        "e2e_backend",
        "PASS",
        "killed == [S-own-1]; S-att-1 is in `running` and named by `refused`; "
        f"the pane {pane} is gone from the shepherd-qa socket; S-own-1 has ended_at "
        "and S-att-1 does not; the project's fate matches `deleted`; one "
        "claimed_human audit record; a project.deleted frame iff deleted",
        f"deleted={deleted}; killed={list(answer['killed'])}; failures={failures}; "
        f"frames={window.kinds()}; sessions_left_on_socket={remaining}",
        inferred_row=(
            "`deleted` was an I row (§0 rule 5): the plan read `commit_project_delete` "
            f"as re-deriving and refusing while a live session remains. Measured: {deleted}, "
            "and now PINNED rather than read off the answer — an expectation derived "
            "from the value under test agrees with whatever the product says."
        ),
        measurement=(
            "S11's API row expects kill_failures to contain S-att-1 'with a reason "
            "naming no_pane'. Measured empty: kill_landed turns no_pane into False "
            "and only a raise is recorded as a failure."
        ),
    )


def test_s13_orphan_moves_the_living_and_destroys_the_dead(harness: Harness) -> None:
    """S13 — the third dialog choice, over **P6**, which owns its own pane."""
    _require_binding(harness)
    client, store, seeded = harness.client, harness.store, harness.seeded
    p6 = seeded.project("P6")
    pane = PANES[3]
    assert pane in tmuxctl.sessions(), f"{pane} must be live before the orphan"

    running_ids = {row.id for row in store.running_sessions_for(p6)}
    finished_ids = {seeded.session(label) for label in ("S-fin-4", "S-fin-5", "S-fin-6")}
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    answer = client.delete_project(p6, on_running="orphan")
    assert answer["deleted"] is True, answer
    assert set(answer["orphaned"]) == running_ids, (answer["orphaned"], running_ids)  # type: ignore[arg-type]
    assert set(answer["destroyed"]) == finished_ids, (answer["destroyed"], finished_ids)  # type: ignore[arg-type]
    # **`severed` is populated, and the loop over it can therefore execute.**
    # Before the seed carried a cross-project lineage pair this list was `[]` in
    # every run: `_sever_lineage` only reports a referrer in *another* workspace,
    # nothing seeded a lineage column, and a `for link in severed:` over an empty
    # list asserts nothing while reading as coverage. The pair is S-att-4 (still
    # running, in P3) pointing at S-fin-4 (stopped, in P6) — the case the
    # product's own docstring names.
    severed = answer["severed"]
    assert isinstance(severed, list), severed
    child, parent = seeded.session("S-att-4"), seeded.session("S-fin-4")
    assert len(severed) == 1, (
        f"exactly one lineage link crosses into P6 and must be reported: {severed}"
    )
    for link in severed:
        assert set(link) == {"session_id", "column"}, link
    assert severed[0]["session_id"] == child, (severed, child)
    assert severed[0]["column"] == "retry_of", severed
    # Reported **and** nulled. A delete that reported the link and left the
    # column pointing at a row it then deleted would abort the transaction under
    # `PRAGMA foreign_keys=ON`, which is the whole reason the severing exists.
    survivor = store.get_session(child)
    assert survivor is not None and survivor.retry_of is None, (
        f"S-att-4's retry_of must be NULL after the delete: {survivor}"
    )
    assert store.get_session(parent) is None, "the lineage parent was in P6 and is destroyed"

    for session_id in running_ids:
        row = store.get_session(session_id)
        assert row is not None and row.workspace_id == "unassigned", (session_id, row)
    for session_id in finished_ids:
        assert store.get_session(session_id) is None, f"{session_id} should be gone"
    assert store.get_workspace(p6) is None, "the workspace row must be gone"

    # `orphan` moves the row; it does not touch the pane. A pane that vanished
    # here would mean the orphan path is killing what it promised to keep.
    assert pane in tmuxctl.sessions(), f"{pane} must survive an orphan"

    frames = harness.rig.await_count(mark, 1, "B")
    assert [frame.kind for frame in frames] == ["project.deleted"], frames
    assert len(harness.audit.records_for(audit_mark, "delete_project")) == 1

    # --- the UI row: after a reload the two orphans are under Unassigned ----
    #
    # **This is asserted, not measured and dropped.** The earlier reading counted
    # ids in `#page-flock`'s *innerText* and could never have been non-zero: a
    # card carries its id in `card.dataset.sessionId` (`flock.js:392`), which is
    # an attribute and not text, and the cards only render after drilling into a
    # project (`app.js:165-167`), which this scenario never did. The quantity
    # went into the report's `actual` as `orphans_named_on_flock=0` beside a PASS
    # — a named observation point that came back falsified and was recorded as
    # evidence of success. Reached the way `_drill_to_session` reaches them, it
    # would have gone red on the first run.
    page, console = harness.open(nav="flock", label="S13")
    unassigned = seeded.project("P0")
    page.wait_for_selector(f"#flock-projects [data-project-id='{unassigned}']")
    # P6 is deleted, so its project button must be gone from the same list the
    # orphans' new home appears in.
    assert page.eval_on_selector_all(
        f"#flock-projects [data-project-id='{p6}']", "els => els.length"
    ) == 0, "the deleted project is still listed on the Flock"
    page.click(f"#flock-projects [data-project-id='{unassigned}']")
    page.wait_for_selector("#flock-cards [data-session-id]")
    cards = page.eval_on_selector_all(
        "#flock-cards [data-session-id]", "els => els.map(el => el.dataset.sessionId)"
    )
    head = page.inner_text("#flock-sessions-head").strip()
    console.assert_clean("S13:")

    assert running_ids <= set(cards), (
        f"the Flock does not show the orphaned sessions under Unassigned after a "
        f"reload: expected {sorted(running_ids)} among {cards}"
    )
    assert not (finished_ids & set(cards)), (
        f"a destroyed session is still rendered: {sorted(finished_ids & set(cards))}"
    )

    harness.report.record(
        "S13",
        "integration",
        "PASS",
        "deleted=true; orphaned names both running sessions; destroyed names the "
        "three finished ones; severed carries exactly one {session_id, column} "
        "link — S-att-4's retry_of into P6 — and the column is NULL afterwards; "
        "both survivors belong to unassigned; the three finished rows are gone; "
        f"the workspace row is gone; the pane {pane} still exists; exactly one "
        "project.deleted frame; after a reload the Flock lists no P6 and shows "
        "both orphans as cards under Unassigned, with no destroyed session among "
        "them",
        f"orphaned={list(answer['orphaned'])}; destroyed={list(answer['destroyed'])}; "
        f"severed={severed}; flock_head={head!r}; "
        f"orphan_cards_under_unassigned={sorted(running_ids & set(cards))}; "
        f"cards={cards}",
    )
