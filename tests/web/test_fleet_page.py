"""The fleet page's two server-side truths: the order, and the empty state.

There is no browser on this host, so rendering is a manual checklist (T16's
`human_verify`). What *is* mechanical is that the order the page renders is the
order the system computed — §16's `fleet_sort_key`, never alphabetical, never
mtime, and never re-derived in JavaScript — and that a first run with no
database still has the fields an honest empty state needs (F16).
"""

from __future__ import annotations

import re
from pathlib import Path

from web.conftest import NOW, Client, seed

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import CONFIDENT_ENOUGH, ActionSource, NextActionKind, StopReason
from shepherd.signals.ordering import LIVENESS_WINDOW_S, fleet_sort_key
from shepherd.signals.stop_rules import DEFAULT_ACTIONS, default_actions
from shepherd.store.db import Store
from shepherd.store.models import UNASSIGNED_PROJECT_ID, FleetRow
from shepherd.web import routes

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"

#: The ask §8 raises on an idle session — the actual ask, never "needs attention".
IDLE_ASK = "idle — waiting for your next instruction"


def row(session_id: str, state: SessionState, last_event_at: str | None = NOW) -> FleetRow:
    return FleetRow(
        session_id=session_id,
        engine_session_id="eng",
        workspace_id="w-1",
        workspace_name="shepherd",
        repo_name=None,
        state=state,
        title=None,
        brief=None,
        needs_you_reason=IDLE_ASK if state is SessionState.NEEDS_YOU else None,
        tasks_done=2,
        tasks_total=5,
        active_subagents=3,
        last_event_at=last_event_at,
        cwd="/root/Shepherd",
    )


def test_fleet_ordering() -> None:
    """§16: needs_you first, then running, then the rest — state, not the name."""
    rows = [
        row("z-stopped", SessionState.STOPPED),
        row("a-running", SessionState.RUNNING),
        row("m-needs-you", SessionState.NEEDS_YOU),
    ]
    ordered = [item.session_id for item in sorted(rows, key=lambda item: fleet_sort_key(item, NOW))]
    assert ordered == ["m-needs-you", "a-running", "z-stopped"]
    # …and alphabetical order is a different answer, so the assertion has teeth.
    assert ordered != sorted(item.session_id for item in rows)


def test_a_silent_running_session_is_demoted_not_hidden() -> None:
    """§8's read-time backstop: silence past the window is not `running`."""
    stale = row("a-stale", SessionState.RUNNING, last_event_at="2026-09-16T09:00:00Z")
    live = row("b-live", SessionState.RUNNING)
    assert LIVENESS_WINDOW_S == 90
    ordered = [
        item.session_id for item in sorted([stale, live], key=lambda i: fleet_sort_key(i, NOW))
    ]
    assert ordered == ["b-live", "a-stale"]


def test_needs_you_reason_carries_the_actual_ask(client: Client, store: Store) -> None:
    """§8: the reason is what to do, never "session needs attention"."""
    session = seed(store)
    store.apply_fold_delta(
        session.id,
        FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=IDLE_ASK, last_event_at=NOW),
    )
    data = client.request("/api/fleet").json()["data"]
    assert isinstance(data, dict)
    listed = data["needs_you"]
    assert isinstance(listed, list)
    assert listed[0]["needs_you_reason"] == IDLE_ASK
    assert "needs attention" not in str(listed)


def test_empty_fleet_payload_renders_an_empty_state(client: Client) -> None:
    """F16: a fresh install is the first thing anyone sees — honest, not blank."""
    data = client.request("/api/fleet").json()["data"]
    assert isinstance(data, dict)
    assert data["session_count"] == 0
    assert data["needs_you"] == []
    discovery = data["discovery"]
    assert isinstance(discovery, dict)
    # The two facts the empty-state panel names: hooks, and the registry count.
    assert discovery["hooks"] == "unknown"
    assert discovery["registry_sessions"] == 0

    projects = client.request("/api/projects").json()["data"]
    assert isinstance(projects, dict)
    # E21/N1: a fresh install is not empty — migration 004 seeds the reserved
    # project, and it is the one row `/api/projects` answers with here.
    assert projects["projects"] == [
        {
            "project_id": UNASSIGNED_PROJECT_ID,
            "name": "Unassigned",
            "description": "Work that matched no declared project.",
            "repo_count": 0,
            "last_activity_at": None,
        }
    ]


def test_the_page_has_an_empty_state_to_render_it_into() -> None:
    """The panel is static markup the script fills — not markup it builds."""
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="empty-state"' in markup
    assert "no sessions discovered yet" in markup

    fleet = (STATIC_ROOT / "fleet.js").read_text(encoding="utf-8")
    assert "empty-state" in fleet
    assert "registry_sessions" in fleet
    assert "hooks" in fleet


def test_the_page_does_not_re_derive_the_order() -> None:
    """Ordering is computed server-side; the page renders what it was handed."""
    fleet = (STATIC_ROOT / "fleet.js").read_text(encoding="utf-8")
    for shape in (".sort(", "localeCompare", "FLEET_STATE_ORDER"):
        assert shape not in fleet, shape


def test_the_fleet_route_hands_the_page_an_ordered_tree(client: Client, store: Store) -> None:
    """§16 over HTTP (BLOCKER T16-1): the order arrives from the server.

    The three rows are created stopped-first, so creation order and state order
    disagree; whatever the page does with this payload, `needs_you` is already
    at the top when it gets there.
    """
    workspace = store.create_project(name="shepherd", description=None)
    made: dict[str, str] = {}
    for engine_id, state in (
        ("eng-stopped", SessionState.STOPPED),
        ("eng-running", SessionState.RUNNING),
        ("eng-needs-you", SessionState.NEEDS_YOU),
    ):
        session = store.register_session(
            engine_session_id=engine_id,
            workspace_id=workspace.id,
            repo_id=None,
            cwd="/root/Shepherd",
            started_at="2026-09-16T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        store.apply_fold_delta(session.id, FoldDelta(state=state, last_event_at=NOW))
        made[engine_id] = session.id

    data = client.request("/api/fleet/tree").json()["data"]
    assert isinstance(data, dict)
    workspaces = data["workspaces"]
    assert isinstance(workspaces, list)
    sessions = workspaces[0]["sessions"]
    assert [row["session_id"] for row in sessions] == [
        made["eng-needs-you"],
        made["eng-running"],
        made["eng-stopped"],
    ]


def test_the_page_reads_the_ordered_tree_rather_than_a_flat_list() -> None:
    """The wiring half: the page asks for the tree the server ordered."""
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert "/api/fleet/tree" in app
    fleet = (STATIC_ROOT / "fleet.js").read_text(encoding="utf-8")
    # Grouping now arrives with the payload; the page no longer builds it.
    assert "groupByWorkspace" not in fleet
    assert "view.workspaces" in fleet


# ----- T15: the stopped row, its actions, and the honest `[why?]` -------------
#
# There is no browser and no JS runtime on this host, so what follows proves two
# different things and says which is which: the **payload** half runs over HTTP
# against a real store, and the **rendering** half is a scan of the bytes the
# server serves. A scan can show that the shipped source has the branch and the
# wording; it cannot show a pixel. The pixels are T15's human checkpoint.

#: `const ACTION_MILESTONE = { resume: "M3", … }` — the table RD6 requires.
_MILESTONE_TABLE = re.compile(r"const\s+ACTION_MILESTONE\s*=\s*\{(.*?)\n\}", re.DOTALL)
_LIVE_TABLE = re.compile(r"const\s+LIVE_KINDS\s*=\s*\{(.*?)\n\}", re.DOTALL)
_ENTRY = re.compile(r"(\w+):\s*\"?([\w]+)\"?")

#: Any `"/api/…"` literal the shipped page holds.
_API_LITERAL = re.compile(r"\"(/api/[^\"]*)\"")


def fleet_js() -> str:
    return (STATIC_ROOT / "fleet.js").read_text(encoding="utf-8")


def function_body(source: str, name: str) -> str:
    """The text of one top-level function, up to the next one."""
    start = source.index(f"function {name}(")
    rest = source[start + 1 :]
    end = rest.find("\nfunction ")
    tail = rest.find("\nexport function ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


def test_stopped_row_renders_why_and_first_action(client: Client, store: Store) -> None:
    """§12's collapsed row: the chip, one line of `why`, the first action."""
    source = fleet_js()
    collapsed = function_body(source, "stoppedRow")
    assert "session-why" in collapsed
    assert "actions[0]" in collapsed
    assert "bucketChip" in function_body(source, "sessionRow")
    # …and it is only drawn for a row that actually stopped.
    assert "isStopped" in function_body(source, "sessionRow")


def test_expanded_row_lists_every_action_with_its_source() -> None:
    """Expanding lists every action with its ordinal and where it came from."""
    body = function_body(fleet_js(), "expansion")
    assert "index + 1" in body
    assert "action.source" in body or "sourceFooter" in body
    assert "action-source" in body


def test_source_footer_counts_by_source() -> None:
    """At M2 the footer always reads `N heuristic` — which is the honest signal.

    Not because the footer hard-codes the word: because **every** action this
    build can produce carries `ActionSource.HEURISTIC`, so a footer that counted
    anything else would be counting something nothing writes (D34's lane is off).
    """
    assert "function sourceFooter" in fleet_js()
    produced = {
        action.source
        for actions in DEFAULT_ACTIONS.values()
        for action in actions
    }
    assert produced == {ActionSource.HEURISTIC}
    assert (
        default_actions(
            StopReason.COMPLETED, confidence=0.5, missing=(), waiting_on=None
        )[0].source
        is ActionSource.HEURISTIC
    )


def test_why_is_a_note_not_a_button_without_the_lane() -> None:
    """N10: a button that fires nothing is worse than no button.

    `[why?]` is a native disclosure — it expands the heuristic evidence the row
    already carries and says, in words, that the model lane is not built. It
    must not imply a verdict nobody computed.
    """
    source = fleet_js()
    body = function_body(source, "whyNote")
    assert 'element("details"' in body
    assert 'element("summary"' in body
    assert 'element("button"' not in body
    assert "addEventListener" not in body

    note = re.search(r"MODEL_LANE_NOTE\s*=\s*\n?\s*\"([^\"]+)\"", source)
    assert note is not None, "the honest note is a named constant"
    wording = note.group(1).lower()
    assert "not built" in wording or "not available" in wording
    assert "model" in wording


def test_unreachable_action_kinds_are_labelled_not_silently_dead() -> None:
    """RD6: `not yet`, with the milestone named — never an unlabelled dead button."""
    source = fleet_js()
    milestones = dict(_ENTRY.findall(_MILESTONE_TABLE.search(source).group(1)))
    live = dict(_ENTRY.findall(_LIVE_TABLE.search(source).group(1)))

    assert milestones == {
        "resume": "M3",
        "respawn": "M3",
        "retry": "M3",
        "escalate": "M4",
        "requeue": "M4",
        "reauth": "M4",
    }
    # Totality: every kind the store can hold is either live or labelled. A kind
    # in neither table is exactly the silent dead button this test forbids.
    assert set(milestones) | set(live) == {kind.value for kind in NextActionKind}

    body = function_body(source, "actionButton")
    assert "disabled" in body
    assert "not yet" in body
    assert ".title" in body


def test_external_action_with_a_target_is_a_link() -> None:
    """§12's `[↗]`: a live affordance at M2, because it needs nothing of ours."""
    body = function_body(fleet_js(), "actionButton")
    assert 'element("a"' in body
    assert "action.target" in body
    assert "noopener" in body


def test_external_action_without_a_target_is_not_a_link() -> None:
    """G-M2-7: `Chase — what it is waiting on is not recorded` has no url.

    Nothing at M2 can name what a session is waiting on (`waiting_on` is always
    `None`), so the one captured `external` default carries no target and the
    row must not pretend to a destination it does not have.
    """
    chase = DEFAULT_ACTIONS[StopReason.BLOCKED_EXTERNAL][0]
    assert chase.kind is NextActionKind.EXTERNAL
    assert chase.target is None

    body = function_body(fleet_js(), "actionButton")
    # The link branch is guarded on the target being a non-empty string.
    assert 'typeof action.target === "string"' in body


def test_expansion_reads_no_log_and_no_transcript() -> None:
    """K14 / D25: everything the expansion shows is already in the row."""
    assert "fetch(" not in fleet_js()
    # T19: `TERMINAL_WS_PATH` joins the two paths that are deliberately not
    # calls. `routes.py` says it in words — "an upgrade is not a call, exactly
    # as `SSE_PATH` is not one" — and `terminal.js` is the page that opens it.
    # T19 remediation: `POST_ROUTES` joins the set because the page now has a
    # mutation to make — D29's local rename, which `index.html` shipped an
    # affordance for and nothing wired. The rule is unchanged: every `/api/...`
    # literal in the shipped JS is a path `routes.py` declares.
    known = (
        set(routes.API_ROUTES)
        | set(routes.POST_ROUTES)
        | {routes.SSE_PATH, routes.TERMINAL_WS_PATH}
    )
    for path in sorted(STATIC_ROOT.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for literal in _API_LITERAL.findall(source):
            assert literal in known, f"{path.name}: {literal}"
        for shape in (".jsonl", "file://", "/logs", ".claude"):
            assert shape not in source, f"{path.name}: {shape}"


def test_row_with_zero_actions_is_only_a_confident_completed() -> None:
    """§14's rule, and the page's honest line when it is the one that applies.

    An empty action list on anything but a confident `completed` is a test
    failure — including DP10's 0.5 completion, which is the common case and
    carries `Review the diff` precisely so the row is never a green dead end.
    """
    for reason in StopReason:
        actions = default_actions(
            reason, confidence=CONFIDENT_ENOUGH, missing=(), waiting_on=None
        )
        if reason is StopReason.COMPLETED:
            assert actions == ()
        else:
            assert actions != (), reason
    low = default_actions(
        StopReason.COMPLETED, confidence=0.5, missing=(), waiting_on=None
    )
    assert [action.text for action in low] == ["Review the diff"]

    assert "session-no-action" in function_body(fleet_js(), "stoppedRow")
