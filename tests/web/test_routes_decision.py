"""T8.2: `get_decision` and its route, driven over HTTP against frozen captures.

**Seam: `Client` over the shipped route table**, which is the seam Phase 8 names
for this half — the tool is reached exactly the way a browser reaches it, through
`resolve()` and `invoke()`, and nothing here calls the handler.

The pane the server reads is a **real capture** under `docs/probes/`, classified
by the shipped `read_pane` and parsed by T8.1's `read_decision`. The expected
labels below are copied from `docs/design/decision-card-shapes.md`, which copies
them from the capture — never re-derived by running the parser twice, which is
the tautology that would make every assertion here pass by construction.

The three mandatory degradations each have a case: an **attached** session (no
pane of ours at all), an **unparseable** dialog (the ask and no choices, never a
guess), and the **trust** dialog (named, with the cursor reported and never
interpreted — a blind Enter there answers *"No, exit"*).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from web.conftest import Client

from shepherd.core.runner import PaneKind, PaneState, ProcState, RunnerHandle
from shepherd.core.states import Origin, Ownership
from shepherd.runner.base import PaneRef
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store
from shepherd.store.models import Session
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"

#: The `*-fmt.txt` line recorded beside each capture, in `PANE_FORMAT` order and
#: redacted the way `tests/runner/test_pane.py` redacts it. Keyed by capture,
#: because the trust screen was taken with the alternate screen **off** and a
#: single shared line would classify it as something it is not.
FIELDS = {
    "06-permission-dialog.ansi": "1|0||✳ shp-probe-title-1|160|45|4041880",
    "01-trust-dialog.ansi": "0|0||<redacted: host name>|160|45|4041880",
    "03-after-stop.ansi": "1|0||✳ Claude Code|160|45|4041880",
}

#: `docs/design/decision-card-shapes.md` shape 1, verbatim. **Choice 2 is why
#: U11 refuses to flatten this to approve/reject**: it carries the scope.
PERMISSION_CHOICES = [
    {"number": 1, "label": "Yes", "selected": True},
    {
        "number": 2,
        "label": "Yes, and always allow access to /tmp/shp-tui-A-4tvrx00n from this project",
        "selected": False,
    },
    {"number": 3, "label": "No", "selected": False},
]

#: Shape 2. Unnumbered, and the cursor is on the **refusal**.
TRUST_CHOICES = [
    {"number": None, "label": "No, exit", "selected": True},
    {"number": None, "label": "Yes, I trust this folder", "selected": False},
]

NOW = "2026-09-16T10:00:30Z"


def pane_of(capture: str) -> PaneState:
    """One `PaneState` off a frozen capture, through the shipped classifier."""
    return read_pane((RUN / capture).read_bytes(), parse_pane_fields(FIELDS[capture]), [])


@pytest.fixture()
def pane(request: pytest.FixtureRequest) -> PaneState:
    """The screen the scripted runner will answer with.

    Overridden per test by `@pytest.mark.parametrize("pane", [...], indirect=True)`:
    a capture name, or a `PaneState` a test built for a degradation no capture
    shows.
    """
    wanted = getattr(request, "param", "06-permission-dialog.ansi")
    return wanted if isinstance(wanted, PaneState) else pane_of(wanted)


@pytest.fixture()
def scripted_runner(pane: PaneState) -> ScriptedRunner:
    """`tests/web/conftest.py`'s runner, with this module's pane in it."""
    return ScriptedRunner(
        panes=(pane,),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=(RUN / "06-permission-dialog.ansi").read_bytes(),
        owned_panes=(),
    )


def owned(store: Store, runner: ScriptedRunner) -> Session:
    """A session with a pane of ours — the only kind `get_decision` can read.

    Both halves, because either one alone is a different session: the store row
    carries the handle, and the runner is told it owns that pane. A fixture that
    invented a pane for any handle would let this suite pass against a driver
    that exits non-zero on an unknown target.
    """
    workspace = store.create_project(name="shepherd", description=None)
    session = store.register_session(
        engine_session_id="eng-owned",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.USER_UI,
        ownership=Ownership.OWNED,
    )
    store.set_runner_handle(
        session.id,
        RunnerHandle(
            runner=RUNNER_NAME,
            socket=SCRIPTED_SOCKET,
            session_name=f"shepherd_{session.id}",
        ),
    )
    runner.live[f"shepherd_{session.id}"] = PaneRef(
        session_name=f"shepherd_{session.id}",
        session_id=session.id,
        pane_pid=4041880,
        dead=False,
    )
    return session


def decision(client: Client, session_id: str) -> dict[str, object]:
    answer = client.request(f"/api/sessions/{session_id}/decision")
    assert answer.status == 200, answer.body
    body = answer.json()
    assert body["ok"] is True, body
    data = body["data"]
    assert isinstance(data, dict)
    return data


# ----- U11: the engine's own prompt, with its numbered choices ---------------


def test_the_route_answers_the_engines_own_prompt_with_its_own_numbering(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """U11, end to end. The numbers are labels the engine drew, not positions.

    The whole of the expected value is the design doc's copy of the capture, so
    a parser that renumbered, reordered or dropped the scope-carrying option
    fails here rather than agreeing with itself.
    """
    session = owned(store, scripted_runner)
    data = decision(client, session.id)
    assert data["ok"] is True, data
    assert data["asking"] is True
    assert data["readable"] is True
    assert data["pane_kind"] == PaneKind.PERMISSION_DIALOG.value
    assert data["choices"] == PERMISSION_CHOICES
    assert data["text"] == (
        "Bash command\n"
        "  touch perm-probe.txt\n"
        "  Create an empty file named perm-probe.txt\n"
        "Do you want to proceed?"
    )


@pytest.mark.parametrize("pane", ["01-trust-dialog.ansi"], indirect=True)
def test_the_trust_dialog_is_named_and_its_cursor_is_reported_never_interpreted(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """C15/E17 on the wire. The cursor sits on *No, exit* and the answer says so.

    Nothing in the projection calls the selected option a default, an
    affirmative or a safe one: it reports **which line carries the cursor**, and
    the page is told which dialog it is by name so it can refuse to answer it
    blind.
    """
    session = owned(store, scripted_runner)
    data = decision(client, session.id)
    assert data["pane_kind"] == PaneKind.TRUST_DIALOG.value
    assert data["choices"] == TRUST_CHOICES
    assert "affirmative" not in str(data) and "default" not in str(data)


@pytest.mark.parametrize("pane", ["03-after-stop.ansi"], indirect=True)
def test_an_idle_pane_is_not_asking_anything(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """E20's server half: a prompt-ready pane has no ask and offers no choices.

    A card built for an idle session is U11 upside down, and the page can only
    refuse to build one if the answer distinguishes "no dialog" from "a dialog I
    could not read" — which is what `asking` is for.
    """
    session = owned(store, scripted_runner)
    data = decision(client, session.id)
    assert data["asking"] is False
    assert data["readable"] is False
    assert data["choices"] == []
    assert data["text"] is None
    assert data["pane_kind"] == PaneKind.PROMPT_READY.value


def _unparseable() -> PaneState:
    """The permission capture with its footer line deleted — one degradation.

    Built from the frozen bytes rather than hand-written, so what is being read
    is a real screen with one real thing wrong with it. `read_decision` finds no
    footer, cannot bound the choice block, and returns `None`.
    """
    intact = pane_of("06-permission-dialog.ansi")
    assert intact.dialog_text is not None
    mutilated = "\n".join(
        line for line in intact.dialog_text.split("\n") if "Esc to cancel" not in line
    )
    assert mutilated != intact.dialog_text, "the mutilation changed nothing"
    return PaneState(
        kind=intact.kind,
        fields=intact.fields,
        input_text=intact.input_text,
        ghost_text=intact.ghost_text,
        dialog_text=mutilated,
    )


@pytest.mark.parametrize("pane", [_unparseable()], indirect=True)
def test_an_unparseable_dialog_answers_the_ask_and_never_guesses_the_choices(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """E16 on the wire, and the rule U17 states: degrade, never guess.

    The screen is still there and is still asking something, so the ask is
    carried verbatim — and `choices` is **empty**, because inventing
    approve/reject as if the engine had drawn them is exactly the guess that
    makes choice 2's scope unreachable without anybody noticing.
    """
    session = owned(store, scripted_runner)
    data = decision(client, session.id)
    assert data["asking"] is True
    assert data["readable"] is False
    assert data["choices"] == []
    assert isinstance(data["text"], str)
    assert "Do you want to proceed?" in data["text"]


def test_an_attached_session_has_no_pane_of_ours_to_read(
    client: Client, store: Store
) -> None:
    """E18's server half: we have no pty of theirs, and the answer says so.

    `no_pane` is the one shape every terminal tool answers with here, so the
    page gets a value it can render rather than a 500 — and the reason names
    the three worlds a caller cannot act on differently.
    """
    workspace = store.create_project(name="theirs", description=None)
    session = store.register_session(
        engine_session_id="eng-attached",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    data = decision(client, session.id)
    assert data["ok"] is False
    assert "attached" in str(data["reason"])
    assert "choices" not in data


def test_the_route_is_a_read_and_writes_no_key(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """The read path may not answer the dialog it just read.

    This is the property C15 turns into a reboot-shaped risk one screen over: a
    module that can read the trust dialog and also press a key on it is one
    refactor away from pressing Enter, which answers *"No, exit"*. The runner
    records every write byte for byte, so the assertion is on the driver rather
    than on a promise in a docstring.
    """
    session = owned(store, scripted_runner)
    decision(client, session.id)
    assert scripted_runner.writes == []
