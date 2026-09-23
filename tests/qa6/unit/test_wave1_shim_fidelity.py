"""W5 — the fake engine's pane classifies as the product expects (shim fidelity).

The premise of every shim-pane scenario (test-plan §3 SHIM-DEPENDENTS): spawn
polls a pane until PROMPT_READY / TRUST_DIALOG / DEAD for up to 60 s, and a
bare `cat` pane classifies UNREADABLE, so a shim that did not print the captured
macOS prompt-ready frame would land every spawn in `needs_you` after 60 s.

A harness-owned tmux server on `-L shepherd-m3-q6<pid>-0` (k = 0 is reserved
for this; absolute tmux path; `-L` on every call; killed at the end on that
socket only). Three 160×45 panes: (a) the default shim, (b) the bare negative
control, (c) U14's dialog mode. Each is classified with the product's own code:
`list-sessions -F LISTING_FORMAT` parsed by `parse_pane_fields`, `capture-pane
-e -p` classified by `read_pane` — the calls `LocalRunner.pane()` makes.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from shepherd.core.runner import PaneKind, PaneState
from shepherd.runner.local import LISTING_FORMAT
from shepherd.runner.pane import FIELD_SEPARATOR, parse_pane_fields, read_pane

from .. import tmuxctl
from ..pool import close_tmux_socket
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Blocked, Recorder, observe

PANES = {"a": ("qa6w5a", "default"), "b": ("qa6w5b", "bare"), "c": ("qa6w5c", "dialog")}
#: (a) must classify within 1 s of the pane starting (W5 tmux row).
READY_BOUND_S = 1.0
#: (c): the shim's own 2 s delay, then the dialog; observed up to 6 s.
DIALOG_BOUND_S = 6.0


class Panes:
    def __init__(self, run: RunContext) -> None:
        self.run = run
        self.socket = run.runner_socket(0)
        self.started: dict[str, float] = {}

    def start(self, key: str) -> None:
        name, mode = PANES[key]
        shim = str(self.run.shims / "claude")
        tmuxctl.run(
            self.socket, self.run.pid, "new-session", "-d", "-s", name, "-x", str(tmuxctl.PANE_COLS),
            "-y", str(tmuxctl.PANE_ROWS), "-e", f"QA6_SHIM_MODE={mode}", "-e", f"HOME={self.run.run0}",
            shim, "--qa6-w5",
        )
        self.started[key] = time.monotonic()

    def classify(self, key: str) -> PaneState | None:
        name, _mode = PANES[key]
        listing = tmuxctl.run(self.socket, self.run.pid, "list-sessions", "-F", LISTING_FORMAT, check=False)
        fields = None
        for line in listing.stdout.splitlines():
            session, separator, rest = line.partition(FIELD_SEPARATOR)
            if separator and session == name:
                fields = parse_pane_fields(rest)
        if fields is None:
            return None
        capture = tmuxctl.run_bytes(self.socket, self.run.pid, "capture-pane", "-e", "-p", "-t", tmuxctl.target(name))
        return read_pane(capture, fields)

    def current_command(self, key: str) -> str:
        name, _mode = PANES[key]
        done = tmuxctl.run(self.socket, self.run.pid, "list-panes", "-t", tmuxctl.target(name), "-F",
                           "#{pane_current_command}")
        return done.stdout.strip()


@pytest.fixture(scope="module")
def panes(qa6_run: RunContext) -> Iterator[Panes]:
    holder = Panes(qa6_run)
    if tmuxctl.server_running(holder.socket, qa6_run.pid):
        raise Blocked(f"a server is already running on {holder.socket}")
    yield holder
    problems = close_tmux_socket(qa6_run, holder.socket)
    for problem in problems:
        qa6_run.teardown_problem("W5", problem)
    if problems:
        raise AssertionError(f"W5 teardown: {problems}")


@scenario("W5")
def test_w5_shim_pane_classifies_prompt_ready(panes: Panes, rec: Recorder) -> None:
    for key in ("a", "b", "c"):
        panes.start(key)

    def kind_is(key: str, wanted: PaneKind) -> PaneState | None:
        state = panes.classify(key)
        return state if state is not None and state.kind is wanted else None

    ready, elapsed = observe(lambda: kind_is("a", PaneKind.PROMPT_READY), READY_BOUND_S + 0.5)
    last_a = panes.classify("a")
    rec.check("tmux.a_prompt_ready", ready is not None and elapsed <= READY_BOUND_S + 0.5,
              f"PROMPT_READY within {READY_BOUND_S}s of the pane starting",
              f"{last_a.kind if last_a else None} after {elapsed:.2f}s")
    rec.equal("tmux.a_input_text_empty", "", ready.input_text if ready is not None else None)

    # (b) the negative control is given the same bound, and must NOT classify.
    unreadable, _ = observe(lambda: kind_is("b", PaneKind.UNREADABLE), READY_BOUND_S + 0.5)
    state_b = panes.classify("b")
    rec.check("tmux.b_unreadable", unreadable is not None and state_b is not None and state_b.kind is PaneKind.UNREADABLE,
              "UNREADABLE (the classifier discriminates)", state_b.kind if state_b else None)

    dialog, elapsed_c = observe(lambda: kind_is("c", PaneKind.PERMISSION_DIALOG), DIALOG_BOUND_S)
    state_c = panes.classify("c")
    if dialog is not None:
        rec.check("tmux.c_permission_dialog", True, "PERMISSION_DIALOG ~2 s later", f"after {elapsed_c:.2f}s")
    else:
        # Recorded, not failed: the plan predicts (c) may not classify on macOS
        # (its capture is Linux). U14 reads this clause and becomes BLOCKED(fixture).
        rec.record("tmux.c_permission_dialog",
                   f"NOT PERMISSION_DIALOG: {state_c.kind if state_c else None} — the Linux dialog capture does not "
                   "classify on macOS; U14 becomes BLOCKED(fixture)")
    rec.note(f"W5(c)={'PERMISSION_DIALOG' if dialog is not None else (state_c.kind.value if state_c else 'none')}")

    for key in ("a", "b", "c"):
        command = panes.current_command(key)
        rec.check(f"proc.{key}_current_command", command in ("sh", "cat", "claude", "bash"),
                  "the shim or cat", command)
    rec.finish()
