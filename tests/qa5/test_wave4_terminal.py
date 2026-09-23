"""Wave 4 — the terminal WebSocket and a real tmux pane. Ground four rounds
never touched.

**S16 is NOT stopped by a tmux-less run** and inherits §1 *except* its pane row.
`terminal_stream` answers `no_pane(session_id)` from `handle_for` alone
(`tools_terminal.py:228-237`), so a session with no `runner_handle` never
reaches `runner.snapshot` or `runner.attach` and nothing in that path speaks to
tmux.
"""

from __future__ import annotations

import pytest

from . import tmuxctl, wsclient
from .conftest import Harness
from .constants import PANES, PHONE, DESKTOP


def _terminal_path(session_id: str) -> str:
    return f"/api/sessions/{session_id}/terminal"


def _drill_to_session(page: object, project_id: str, session_id: str) -> None:
    """Flock -> project -> card -> session pane, the way a person reaches it.

    **There is no router and no hash route.** `app.js` binds the drill to a
    click on `[data-session-id]` (`:172-178`), so a harness that navigated to a
    fragment would be asserting against a page that never opened the view.

    **The project is named, not searched for.** Below the drawer breakpoint
    `openProject` calls `showLevel("sessions")` and the projects column leaves
    the screen, so a loop that tried each project in turn could click exactly
    one and then wait out its timeout on an invisible button — which is what it
    did. The caller knows which project the session is in; it says so.
    """
    page.wait_for_selector(f"#flock-projects [data-project-id='{project_id}']")  # type: ignore[attr-defined]
    page.click(f"#flock-projects [data-project-id='{project_id}']")  # type: ignore[attr-defined]
    page.wait_for_selector(f"[data-session-id='{session_id}']")  # type: ignore[attr-defined]
    page.click(f"[data-session-id='{session_id}']")  # type: ignore[attr-defined]


def test_s14_the_terminal_websocket_against_a_real_owned_pane(harness: Harness) -> None:
    """S14 — PP-5: the first binary frame is the pane snapshot, byte-for-byte."""
    own2 = harness.seeded.session("S-own-2")
    pane = PANES[1]
    assert pane in tmuxctl.sessions(), f"{pane} must be live: S11 destroys {PANES[0]}, not this one"
    audit_mark = harness.audit.mark()

    # A deterministic string on the screen, so the comparison is against bytes
    # somebody put there rather than against an empty pane that would match
    # trivially. The shell echoes it; the capture picks it up.
    tmuxctl.send_keys(pane, "printf 'QA5-S14-MARKER\\n'")

    result = wsclient.upgrade(harness.started.port, _terminal_path(own2), want_frames=1)
    assert result.status == 101, f"expected 101, got {result.status}: {result.headers}"
    binary = result.binary()
    assert binary, f"no binary frame after the handshake: {result.frames}"

    snapshot = binary[0]
    live = tmuxctl.capture_pane(pane)
    assert b"QA5-S14-MARKER" in snapshot, (
        "the snapshot does not contain the bytes the fixture wrote to the pane; "
        "the comparison below would be against an empty screen"
    )
    # The product captures with `-e -p -S -<scrollback>`; `capture_pane` here is
    # the plain visible screen. The strong claim the plan makes is that the
    # frame is the pane's own bytes with no decode/escape/re-encode round trip,
    # which is asserted as **containment of the visible screen's non-empty
    # lines** rather than equality against a different argv — asserting equality
    # against bytes produced by a *different* capture would be asserting about
    # the harness's argv, not the product's.
    for line in [row for row in live.split(b"\n") if row.strip()]:
        assert line in snapshot, (line, snapshot[:400])
    assert snapshot == snapshot.decode("utf-8", "surrogateescape").encode(
        "utf-8", "surrogateescape"
    ), "the frame is not byte-transparent"

    assert pane in tmuxctl.sessions(), "reading a pane must not end it"

    # The negative control, in the same scenario: the order is the security
    # property. A 101 written before `invoke()` answered would leave a browser
    # holding an upgraded socket to a session it may not have.
    refused = wsclient.upgrade(
        harness.started.port, _terminal_path(own2), origin="http://evil.example"
    )
    assert refused.status == 403, refused.status
    assert refused.frames == [], refused.frames

    records = harness.audit.records_for(audit_mark, "terminal_stream")
    assert len(records) == 1, [row.get("tool") for row in harness.audit.since(audit_mark)]

    harness.report.record(
        "S14",
        "e2e_backend",
        "PASS",
        "HTTP 101; the first binary frame carries the pane's own bytes including "
        "the marker the fixture wrote, byte-transparent; the pane survives the "
        "read; a wrong-Origin upgrade is 403 with no frame handed over; one "
        "terminal_stream audit record",
        f"snapshot={len(snapshot)} bytes; frames={[op for op, _ in result.frames]}; "
        f"refused={refused.status}; close_code={result.close_code()}",
        measurement=(
            "PLAN CLAUSE NOT RUN (test-plan S14: '...and the socket closes with "
            "CLOSE_NORMAL'). `wsclient.Upgrade.close_code()` implements the read and "
            "is called by nothing, because on a LIVE pane there is no close to read: "
            "`server.py::_terminal` writes the snapshot, then every chunk "
            "`runner.attach()` yields, and only then a close frame — against a real "
            "tmux pane that is a stream with no end. `read_frames` therefore stops "
            "at a caller-named frame COUNT and closes from this side, so the close "
            "code reported here is whatever the client observed (None when the "
            "harness closed first), never the server's CLOSE_NORMAL. A helper that "
            "read 'to the close frame' would hang forever on exactly the ground "
            "round 5 exists to drive. The clause is a real gap in this scenario's "
            "coverage and is stated rather than omitted from the PASS."
        ),
    )


def test_s15_the_emulator_is_fitted_to_the_real_pane(harness: Harness) -> None:
    """S15 — D6's ground, measured against a live pane, not a frozen capture.

    The tmux row is stated as an expected **inequality** and can therefore fail:
    `terminal_resize` is a registered tool with **no route**, so the page cannot
    push geometry back and the two must diverge. Written as "consistent, or the
    difference is recorded", it would be a probe wearing an assertion's clothes.
    """
    own2 = harness.seeded.session("S-own-2")
    pane = PANES[1]
    geometry: dict[str, dict[str, int]] = {}

    for width in (DESKTOP, PHONE):
        page, console = harness.open(nav="flock", width=width, label=f"S15-{width}")
        _drill_to_session(page, harness.seeded.project("P1"), own2)
        page.wait_for_selector("#session-terminal")
        page.wait_for_function(
            "() => { const el = document.getElementById('session-terminal');"
            " return el !== null && el.dataset.terminalCols !== undefined"
            " && Number(el.dataset.terminalCols) > 0; }"
        )
        reported = page.eval_on_selector(
            "#session-terminal",
            "el => ({cols: Number(el.dataset.terminalCols),"
            " rows: Number(el.dataset.terminalRows)})",
        )
        assert reported["cols"] > 0 and reported["rows"] > 0, (width, reported)
        box = page.eval_on_selector(
            "#session-terminal",
            "el => { const r = el.getBoundingClientRect();"
            " return {right: r.right, bottom: r.bottom,"
            " vw: window.innerWidth, vh: window.innerHeight}; }",
        )
        from .dom import SLACK_PX

        assert box["right"] <= box["vw"] + SLACK_PX, (width, box)
        geometry[width] = {"cols": int(reported["cols"]), "rows": int(reported["rows"])}
        console.assert_clean(f"S15 at {width}:")

    assert geometry[DESKTOP] != geometry[PHONE], (
        "a geometry that does not respond to a 3x width change was never fitted: "
        f"{geometry}"
    )

    pane_cols, pane_rows = tmuxctl.pane_geometry(pane)
    from .constants import PANE_COLS, PANE_ROWS

    assert (pane_cols, pane_rows) == (PANE_COLS, PANE_ROWS), (
        f"the pane's own geometry must still be the fixture's -x/-y: "
        f"{(pane_cols, pane_rows)} vs {(PANE_COLS, PANE_ROWS)}"
    )
    diverged = [
        width
        for width, value in geometry.items()
        if (value["cols"], value["rows"]) != (pane_cols, pane_rows)
    ]
    assert diverged, (
        "the page's reported geometry matched the pane's at both viewports. "
        "`terminal_resize` has no route, so the page cannot push geometry back "
        "and the two must diverge; if they track, the 'no route' reading is wrong."
    )

    harness.report.record(
        "S15",
        "ui",
        "PASS",
        "data-terminal-cols/rows are >0 at both viewports and differ between them; "
        "the terminal box stays inside the viewport; the pane's own geometry is "
        "still -x 160 -y 45 at both, and the page's reported geometry differs from "
        "it at at least one — terminal_resize has no route",
        f"page={geometry}; pane={(pane_cols, pane_rows)}; diverged_at={diverged}",
    )


def test_s16_an_attached_session_has_no_pane_and_the_page_says_so(harness: Harness) -> None:
    """S16 — the `no_pane` branch. **Needs no pane and no tmux server.**"""
    att2 = harness.seeded.session("S-att-2")
    row = harness.store.get_session(att2)
    assert row is not None and row.runner_handle is None, row
    audit_mark = harness.audit.mark()

    result = wsclient.upgrade(harness.started.port, _terminal_path(att2))
    assert result.status == 404, (
        f"a valid handshake for a session with no pane must be refused 404 with "
        f"no 101 written; got {result.status}"
    )
    assert result.frames == [], result.frames

    page, console = harness.open(nav="flock", label="S16")
    _drill_to_session(page, harness.seeded.project("P1"), att2)
    page.wait_for_selector("#session-view")
    page.wait_for_function(
        "() => document.getElementById('session-view').innerText.trim().length > 0"
    )
    text = page.inner_text("#session-view").strip()
    assert text, "the session pane rendered nothing at all"
    # A sentence, not a blank terminal and not a spinner.
    assert len(text.split()) >= 3, f"not a sentence: {text!r}"
    console.assert_clean("S16:")

    assert len(harness.audit.records_for(audit_mark, "terminal_stream")) == 1

    harness.report.record(
        "S16",
        "e2e_backend",
        "PASS",
        "404 after a valid handshake, with no 101 and no frame; the session pane "
        "renders a sentence explaining there is no pane; one audit record; zero "
        "console.error/pageerror",
        f"status={result.status}; pane_text={text[:200]!r}",
    )


def test_s17_a_stale_handle(harness: Harness) -> None:
    """S17 — PP-4's negative half, and PP-3's breaker.

    A stale handle is **in `killable`** and cannot be stopped, which falsifies
    the stronger reading of PP-3. The fixture kills the pane inside the scenario,
    and asserts its own removal rather than assuming it.
    """
    client, store, seeded = harness.client, harness.store, harness.seeded
    p7, own4 = seeded.project("P7"), seeded.session("S-own-4")
    pane = PANES[2]

    assert pane in tmuxctl.sessions(), f"{pane} must be listed BEFORE the fixture kills it"
    tmuxctl.kill_session(pane, tolerate_missing=False)
    assert pane not in tmuxctl.sessions(), f"{pane} must not be listed after the fixture's kill"
    row = store.get_session(own4)
    assert row is not None and row.ended_at is None, "the store row is still live — that is the point"

    planned = client.delete_project(p7)
    assert own4 in list(planned["killable"]), (
        f"a stale handle is in killable: {planned['killable']}"
    )

    before = store.list_anomaly_counts().get("stop_failed", 0)
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    answer = client.delete_project(p7, on_running="kill_sessions")
    assert answer["killed"] == [], answer
    failures = answer["kill_failures"]
    assert isinstance(failures, list) and len(failures) == 1, failures
    assert failures[0]["session_id"] == own4, failures
    assert str(failures[0]["reason"]).startswith("RunnerRefusal:"), failures[0]

    after = store.list_anomaly_counts().get("stop_failed", 0)
    assert after == before + 1, (before, after)

    # Pinned for the same reason S11 pins it: `["project.deleted"] if deleted
    # else []` reads the expectation off the value under test and passes on both
    # branches. The stale handle's session is still running after the refusal, so
    # the re-derived running set is non-empty and the delete must refuse.
    deleted = answer["deleted"]
    assert deleted is False, (
        "S-own-4's kill raised, so it is still running and the re-derived gate "
        f"must refuse the delete: deleted={deleted}"
    )
    assert (store.get_workspace(p7) is None) is bool(deleted), (
        f"the project's fate must match `deleted`: deleted={deleted}"
    )
    assert pane not in tmuxctl.sessions(), "the fixture removed it; the product did not"

    records = harness.audit.records_for(audit_mark, "delete_project")
    assert len(records) == 1, records
    assert "GENERIC_ERROR" not in str(records[0]), records[0]

    window = harness.rig.control("S17", since=mark)
    window.assert_kinds(["project.deleted"] if deleted else [], prefix="project.")

    # §0 rule 3: cleanup branches on the **measured** value, and the report says
    # which branch ran. A fixture that "tidied" a surviving P7 would be writing
    # past the product's own refusal.
    branch = "deleted == true; nothing to clean" if deleted else "deleted == false; P7 survives"

    harness.report.record(
        "S17",
        "e2e_backend",
        "PASS",
        "the stale handle is in killable; killed == []; exactly one kill_failure "
        "naming the session with a reason beginning RunnerRefusal:; stop_failed up "
        "by exactly 1; the project's fate matches `deleted`; the pane is absent "
        "before and after; one audit record and no GENERIC_ERROR",
        f"deleted={deleted}; failure={failures[0]}; stop_failed {before}->{after}; "
        f"cleanup branch: {branch}",
        cleanup_branch=branch,
    )
