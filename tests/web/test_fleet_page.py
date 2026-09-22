"""The fleet page's two server-side truths: the order, and the empty state.

There is no browser on this host, so rendering is a manual checklist (T16's
`human_verify`). What *is* mechanical is that the order the page renders is the
order the system computed — §16's `fleet_sort_key`, never alphabetical, never
mtime, and never re-derived in JavaScript — and that a first run with no
database still has the fields an honest empty state needs (F16).

**The filename and every node id here are deliberately unchanged, and the
bodies are not.** M5 renamed the page: `fleet.js` became `flock.js` (U9's three
panes) and D67 moved D21's `next_actions[]` list off the session card into the
session **pane**, because U7 fixes the card at four items. Every property below
therefore still holds — it is simply asserted a module over. Renaming the tests
with the file would have retired seventeen frozen ids to say nothing new, and
`tests/boundaries/test_collected_node_ids.py` is there to make that cost
visible; exactly one id retires in this move, and it retires because its
property genuinely moved rather than because a filename did.
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

    flock = flock_js()
    assert "empty-state" in flock
    assert "registry_sessions" in flock
    assert "hooks" in flock


def test_the_page_does_not_re_derive_the_order() -> None:
    """Ordering is computed server-side; the page renders what it was handed."""
    flock = _CODE_ONLY(flock_js())
    for shape in (".sort(", "localeCompare", "FLEET_STATE_ORDER"):
        assert shape not in flock, shape


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
    flock = flock_js()
    # Grouping now arrives with the payload; the page no longer builds it.
    assert "groupByWorkspace" not in flock
    assert "view.workspaces" in flock


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

#: Both modules explain in prose why `.sort(` and a second `fetch(` are absent,
#: so the two **absence** scans below read the code with its comments removed. A
#: scan that cannot tell a statement from the comment forbidding it fails on the
#: explanation, which trains the next person to delete the explanation.
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def _CODE_ONLY(text: str) -> str:
    return _COMMENTS.sub("", text)


def flock_js() -> str:
    """M5's page module. `fleet.js` is still on disk and is not this file.

    It is dead code awaiting the one commit that rewires `app.js`, and nothing
    in this module reads it: a scan pointed at the module the page no longer
    renders from is the purest form of a test that passes by checking the wrong
    thing.
    """
    return (STATIC_ROOT / "flock.js").read_text(encoding="utf-8")


def session_js() -> str:
    """D67's pane: the home of D21's list and every rule that governs it."""
    return (STATIC_ROOT / "session.js").read_text(encoding="utf-8")


def function_body(source: str, name: str) -> str:
    """The text of one top-level function, up to the next one."""
    start = source.index(f"function {name}(")
    rest = source[start + 1 :]
    end = rest.find("\nfunction ")
    tail = rest.find("\nexport function ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


# `test_stopped_row_renders_why_and_first_action` was **retired here** by D67,
# with its reason and its successor recorded in
# `tests/boundaries/test_collected_node_ids.py`. It asserted that `stoppedRow`
# rendered `session-why` and `actions[0]`; after U7 the card carries four items
# and no row renders either. The property survives at the pane and is asserted
# by `test_the_session_pane_renders_why_and_every_action`, which is strictly
# stronger — `actions[0]` became every action.


def test_expanded_row_lists_every_action_with_its_source() -> None:
    """Every action with its ordinal and where it came from — now in the pane.

    The fleet row *expanded* to show the list because the collapsed row had
    space for one action. The pane has space for it outright (D67), so there is
    no expansion to open and the list is simply there — which is the same
    property with one fewer click, not a weaker one.
    """
    body = function_body(session_js(), "actionList")
    assert "index + 1" in body
    assert "action.source" in body
    assert "action-source" in body

    # **"Every" is the load-bearing word, and a mutation proved it was not being
    # checked.** `actions.slice(0, 1).forEach(...)` keeps the ordinal, the
    # source and the class, so every assertion above stayed green while the pane
    # rendered exactly the one action the retired card test settled for. The
    # truncation is what D67's successor claims to have removed, so the shapes
    # that truncate are named rather than described.
    assert "actions.forEach(" in body
    for truncating in (".slice(", "actions[0]", ".at(0)", "actions.shift("):
        assert truncating not in body, truncating


def test_source_footer_counts_by_source() -> None:
    """The footer's property, kept per row instead of aggregated (D67).

    The fleet row's footer read `N heuristic` because the expansion could not
    afford a source beside each of three actions. The pane can, and does —
    `action-source` on every row — which is strictly more information than the
    count was, so the aggregate is gone rather than lost.

    The honest signal is unchanged and it is not a hard-coded word: **every**
    action this build can produce carries `ActionSource.HEURISTIC`, so a page
    that showed anything else would be showing something nothing writes (D34's
    lane is off).
    """
    assert "action.source" in function_body(session_js(), "actionList")
    assert "sourceFooter" not in session_js(), "the aggregate is gone, not hidden"
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
    source = session_js()
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
    source = session_js()
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

    body = function_body(source, "actionButton") + function_body(source, "notYetReason")
    assert "disabled" in body
    assert "not yet" in body
    assert ".title" in body


def test_external_action_with_a_target_is_a_link() -> None:
    """§12's `[↗]`: a live affordance at M2, because it needs nothing of ours."""
    body = function_body(session_js(), "actionButton")
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

    body = function_body(session_js(), "actionButton")
    # The link branch is guarded on the target being a non-empty string.
    assert 'typeof action.target === "string"' in body


def test_expansion_reads_no_log_and_no_transcript() -> None:
    """K14 / D25: everything the expansion shows is already in the row."""
    # The page that lists sessions opens nothing at all.
    assert "fetch(" not in flock_js()
    # The pane has exactly one call, and it is D29's local rename — a *mutation*
    # the human asked for, declared in `POST_ROUTES`, and not a second read of
    # anything the row already carries. Counted rather than waved past: "the
    # pane may fetch" would retire the rule instead of bounding it.
    assert _CODE_ONLY(session_js()).count("fetch(") == 1
    assert "RENAME_PATH" in function_body(session_js(), "commitRename")
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

    assert "session-no-action" in function_body(session_js(), "actionList")
