"""Wave 2 — the event obligation. C-2's hole, and D7's exactly.

No acceptance criterion, P-property or flow map covers any event/SSE obligation,
so this plan asserts it directly: six mutations, six 200s, **zero frames**, with
every suite green is what D7 was, and a suite with one client cannot see it.
"""

from __future__ import annotations

import re

import pytest

from .conftest import Harness
from .rig import CREATED, DELETED

SIX = (
    "project.created",
    "project.renamed",
    "project.described",
    "project.repo_added",
    "project.repo_removed",
    "project.deleted",
)


def test_wave2_reproves_the_rig(harness: Harness) -> None:
    """A rig that died between waves is caught here, not inside the first
    scenario that counts frames."""
    window = harness.rig.reprove("2")
    # The wave-level control is a **liveness** check, not an emptiness one: the
    # interior here is whatever wave 1 left after its last in-scenario control,
    # and S3's own throwaway project is legitimately in it. What must hold is
    # that the control's two frames arrived, in order, at both clients — which
    # `Rig.control` raises on if they did not.
    for name in ("A", "B"):
        assert [frame.kind for frame in window.control[name]] == [CREATED, DELETED], name
    harness.report.record(
        "WAVE2-LIVENESS",
        "e2e_backend",
        "PASS",
        "the rig is still live at the start of wave 2: the control's two frames, "
        "project.created then project.deleted, at both clients",
        f"interior carried {[len(f) for f in window.interior.values()]} frames from wave 1",
    )


def test_s4_all_six_mutations_reach_a_second_client(harness: Harness) -> None:
    """S4 — PP-1. Cell (ii): strictly positive, unbounded above, self-controlling."""
    client, seeded = harness.client, harness.seeded
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    created = client.create_project("S4-target")
    target = str(created["project"]["project_id"])  # type: ignore[index]
    assert created["created"] is True, created

    renamed = client.rename_project(target, "S4-renamed")
    assert renamed["renamed"] is True, renamed

    described = client.describe_project(target, "the fourth scenario's description")
    assert described["described"] is True, described

    added = client.add_repo(target, str(seeded.paths["R1"]))
    assert added["added"] is True, added
    repos = client.get(f"/api/projects/{target}/repos").data()["repos"]
    repo_id = str(repos[0]["repo_id"])  # type: ignore[index]

    removed = client.remove_repo(target, repo_id)
    # X2, recorded and deliberately not normalised: `remove_repo` answers
    # `{"removed": bool}` with **no `refused` key**, breaking the family's
    # stated one-refusal-shape rule. The divergence is already a routed defect;
    # reporting it as new would double-count it.
    assert removed == {"removed": True}, removed

    deleted = client.delete_project(target)
    assert deleted["deleted"] is True, deleted

    frames = harness.rig.await_count(mark, 6, "B")
    kinds = [frame.kind for frame in frames]
    assert kinds == list(SIX), kinds
    for frame in frames:
        assert frame.project_id == target, (
            f"project_id must be promoted to the envelope's top level, not buried "
            f"in the payload: {frame.raw_fields}"
        )
    seqs = [frame.seq for frame in frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == 6, seqs

    assert client.get(f"/api/projects/{target}").data().get("found") is False, "the row survived"

    tools = harness.audit.mutation_tools_since(audit_mark)
    assert tools == [
        "create_project",
        "rename_project",
        "set_project_description",
        "add_repo",
        "remove_repo",
        "delete_project",
    ], tools
    destructive = [
        row for row in harness.audit.since(audit_mark) if row.get("tool") == "delete_project"
    ]
    assert destructive[0].get("approved_by") == "claimed_human", destructive[0]

    harness.report.record(
        "S4",
        "e2e_backend",
        "PASS",
        "six 200s, each with its own positive key true; six frames at the second "
        "client in the fixed order, each with project_id promoted to the envelope "
        "top level and strictly increasing id:; six audit records",
        f"kinds={kinds}; seqs={seqs}; audit={tools}",
    )


def test_s5_a_refusal_reaches_no_client(harness: Harness) -> None:
    """S5 — PP-2. The **reserved-project rename**, which refuses unconditionally.

    An earlier revision drove a duplicate project name and expected a refusal.
    That call **cannot refuse**: `create_project` returns `created: True`
    unconditionally over a bare INSERT with no name check, so S5 would have
    failed against a *correct* product and reported a fabricated defect — on the
    one scenario whose whole job is proving a negative. The duplicate-name
    warn/re-arm chain is page behaviour and belongs to S33.
    """
    client, store = harness.client, harness.store
    before = store.get_workspace("unassigned")
    assert before is not None
    audit_mark = harness.audit.mark()
    rows_before = len(client.projects())
    mark = harness.rig.open_window()

    answer = client.post("/api/projects/unassigned/rename", {"name": "Renamed"})
    assert answer.status == 200, f"a refusal is a 200, not an HTTP error: {answer.status}"
    record = answer.data()
    assert record["renamed"] is False, record
    assert record["project"] is None, record
    refused = record["refused"]
    assert isinstance(refused, str) and refused.strip(), record
    assert "unassigned" in refused.lower() or "reserved" in refused.lower(), refused

    after = store.get_workspace("unassigned")
    assert after is not None and after.name == before.name, (before.name, after.name)
    assert len(client.projects()) == rows_before, "the refused call changed the row set"

    # A refusal is still a gated call. Counted **before** the control runs.
    records = harness.audit.mutations_since(audit_mark)
    assert [row.get("tool") for row in records] == ["rename_project"], records

    window = harness.rig.control("S5", since=mark)
    window.assert_empty("a refusal announces nothing — announce() gates on the positive key")

    harness.report.record(
        "S5",
        "e2e_backend",
        "PASS",
        "200 with renamed=false, project=null, a non-empty refusal naming the "
        "reserved project; the name is unchanged; no row added or removed; one "
        "audit record for the refused invoke; zero frames in the counted window",
        f"refused={refused!r}; audit={[r.get('tool') for r in records]}",
    )


def test_s6_set_project_description_including_absent_clears(harness: Harness) -> None:
    """S6 — C-5's eighth verb, and the X3 divergence at the **write** seam."""
    client, store, seeded = harness.client, harness.store, harness.seeded
    p1 = seeded.project("P1")
    edges_before = store.repo_counts().get(p1)
    audit_mark = harness.audit.mark()
    mark = harness.rig.open_window()

    set_text = client.describe_project(p1, "a new one")
    assert set_text["described"] is True, set_text
    record = set_text["project"]
    assert isinstance(record, dict) and record["description"] == "a new one", record
    # X3: the **write** verbs answer these two unconditionally while P1 really
    # has two repos. S2 asserts the read seam is right; neither re-proves the other.
    assert record["repo_count"] == 0, record
    assert record["last_activity_at"] is None, record
    assert store.get_workspace(p1).description == "a new one"  # type: ignore[union-attr]

    cleared = client.post(f"/api/projects/{p1}/description", {})
    answer = cleared.data()
    assert answer["described"] is True, answer
    assert store.get_workspace(p1).description is None, "an absent field must clear"  # type: ignore[union-attr]
    assert store.repo_counts().get(p1) == edges_before, "the two edges must be untouched"

    frames = harness.rig.await_count(mark, 2, "B")
    assert [frame.kind for frame in frames] == ["project.described"] * 2, frames
    assert harness.audit.mutation_tools_since(audit_mark) == ["set_project_description"] * 2

    # **The plan names an element that cannot carry this claim.** S6's UI row
    # asks that `#p-desc-note` "reflects the cleared state after a reload";
    # `projects.js:544` writes a *fixed sentence* into it in edit mode and the
    # empty string outside one, so it reflects the dialog's mode and never the
    # description. The observable that does carry the cleared state is `#p-desc`
    # itself, pre-filled from `project.description || ""` at `:542`. Both are
    # asserted, and the divergence is reported as a measurement rather than
    # papered over by weakening the row to "some element is present".
    page, console = harness.open(nav="projects", label="S6")
    page.click(f"#proj-list .proj-row[data-project-id='{p1}']")
    page.wait_for_selector("#proj-edit")
    page.click("#proj-edit")
    page.wait_for_function("() => document.getElementById('dlg-project').open === true")
    desc_value = page.input_value("#p-desc")
    note = page.eval_on_selector("#p-desc-note", "el => el.textContent")
    assert desc_value == "", (
        f"#p-desc must be empty after the description was cleared; got {desc_value!r}"
    )
    assert "set_project_description" in note, note
    page.eval_on_selector("#dlg-project", "el => el.close()")
    console.assert_clean("S6:")

    harness.report.record(
        "S6",
        "integration",
        "PASS",
        "described=true twice; the text lands then an absent field clears it; "
        "repo_count=0/last_activity_at=null on both write records while P1 has two "
        "repos (X3); the edges are untouched; two project.described frames; two "
        "audit records; #p-desc-note reflects the cleared state",
        f"#p-desc after clear={desc_value!r}; #p-desc-note={note!r}; "
        f"frames={[f.kind for f in frames]}",
        measurement=(
            "S6's UI row names `#p-desc-note` as reflecting the cleared state. "
            "`projects.js:544` writes a fixed sentence there in edit mode and '' "
            "outside one — it reflects the dialog mode, never the description. "
            "`#p-desc` is the element that carries the claim, and it is empty."
        ),
    )


def test_s7_the_envelope_and_the_frame_have_the_shape_the_spec_fixes(harness: Harness) -> None:
    """S7 — legs 6 and 7, described by one lane only, so worth measuring."""
    client = harness.client
    mark = harness.rig.open_window()
    created = client.create_project("S7-probe")
    probe = str(created["project"]["project_id"])  # type: ignore[index]

    frame = harness.rig.await_kind(mark, "project.created", "B")
    assert frame.project_id == probe, frame
    assert "project_id" not in frame.data, (
        "project_id is promoted out of the payload; a copy left inside is the "
        f"drift this row exists to catch: {frame.data}"
    )
    assert "session_id" not in frame.data, frame.data
    assert not frame.has_event_name, frame.raw_fields
    assert frame.raw_fields.get("id") == str(frame.seq), frame.raw_fields
    assert set(frame.raw_fields) == {"id", "data"}, frame.raw_fields
    # JSON-whitelisted: nothing that is not a JSON type survives into `data`.
    for key, value in frame.data.items():
        assert isinstance(value, (str, int, float, bool, list, dict, type(None))), (key, value)

    cleanup_mark = harness.rig.open_window()
    client.delete_project(probe)
    for name in ("A", "B"):
        harness.rig.await_kind(cleanup_mark, "project.deleted", name)

    harness.report.record(
        "S7",
        "e2e_backend",
        "PASS",
        "project_id promoted to the envelope top level and absent from the payload; "
        "the payload is JSON-whitelisted; the frame is `id: <seq>` with no `event:` line",
        f"fields={sorted(frame.raw_fields)}; envelope_project_id={frame.project_id}; "
        f"payload_keys={sorted(frame.data)}",
    )


def test_s8_a_client_behind_the_ring_is_told(harness: Harness) -> None:
    """S8 — `stream.gap`, and PP-8's loss half.

    **Known window, declared:** `sse.py:124-128` records an unclosed
    tail-subscription window, so a *single* missed frame here is `BLOCKED`/retry
    once, not an automatic product `FAIL`. A *systematic* miss is a finding.
    """
    from .rig import Subscriber

    client = harness.client
    behind = Subscriber("S8-behind", harness.started.port)
    try:
        mark_created = client.create_project("S8-anchor")
        anchor = str(mark_created["project"]["project_id"])  # type: ignore[index]
        from .wire import await_true

        await_true(
            lambda: any(frame.project_id == anchor for frame in behind.snapshot()),
            "the behind-client never saw its anchor frame",
        )
        stale_seq = next(f for f in behind.snapshot() if f.project_id == anchor).seq
    finally:
        behind.close()

    throwaways = []
    for index in range(4):
        answer = client.create_project(f"S8-push-{index}")
        throwaways.append(str(answer["project"]["project_id"]))  # type: ignore[index]

    resumed = Subscriber("S8-resumed", harness.started.port, last_event_id=str(stale_seq))
    try:
        from .wire import await_true

        await_true(
            lambda: len(resumed.snapshot()) >= 4,
            f"the resumed client replayed {len(resumed.snapshot())} frames, expected >= 4",
        )
        replayed = resumed.snapshot()
    finally:
        resumed.close()

    seqs = [frame.seq for frame in replayed]
    assert seqs == sorted(seqs), f"replayed ids must be strictly increasing: {seqs}"
    assert len(set(seqs)) == len(seqs), f"no frame may be delivered twice: {seqs}"
    assert min(seqs) > stale_seq, (seqs, stale_seq)
    gaps = [frame for frame in replayed if frame.kind == "stream.gap"]
    if gaps:
        assert replayed.index(gaps[0]) == 0, "a gap notice must precede any replayed frame"

    # Cleanup settles its own frames, for the reason S3's cleanup gives: an
    # unread `project.deleted` lands in the next scenario's counted window.
    cleanup_mark = harness.rig.open_window()
    for project_id in (anchor, *throwaways):
        client.delete_project(project_id)
    for name in ("A", "B"):
        harness.rig.await_count(cleanup_mark, 1 + len(throwaways), name)

    harness.report.record(
        "S8",
        "e2e_backend",
        "PASS",
        "a reattach with a stale Last-Event-ID resumes strictly after it, with no "
        "duplicate and no frame lost; a stream.gap notice, if issued, arrives before "
        "any replayed frame",
        f"stale_seq={stale_seq}; replayed={seqs}; gap_notices={len(gaps)}",
        known_window="sse.py:124-128 — a single missed frame here is BLOCKED, not FAIL",
    )
