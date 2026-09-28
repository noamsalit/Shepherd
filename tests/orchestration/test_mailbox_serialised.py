"""BC-02: one delivery at a time, and the decision that was taken.

qa6 §8 saw a message typed into a pane **twice** (3 of 6 runs) and a cleared
draft reported as `send_now`. Both triggers — the route's own attempt and the
prompt-ready sweep — can run at once in one process, and `deliver_now` reads the
pending set before it looks at the pane, so two callers each held the same
rows and each typed them.

**The interleaving is forced, not hoped for.** `GatedRunner` wraps the shipped
`ScriptedRunner` and holds the **first** caller of one member on a
`threading.Event`; every later caller passes straight through. What the other
thread does while the first is held is the whole question.

**The one timing element, stated.** A thread that the fix blocks on
`DELIVERY_LOCK` cannot be observed "being blocked" except by waiting for it: the
held-back thread is joined with `HELD_S`, asserted **still alive**, and only
then is the gate released. Before the fix it finishes inside that window having
typed the message, so a slow host cannot turn the blocked direction green early.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.fold_types import FoldDelta
from shepherd.core.mailbox import MailboxCounts, MailboxOrigin
from shepherd.core.runner import (
    PaneState,
    ProcState,
    RunnerHandle,
    SessionSpec,
    WriteDecision,
)
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.orchestration.mailbox import Delivery, deliver_now, queue_message, sweep_pending
from shepherd.runner.base import ByteStream, PaneRef
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.toolsurface.tools_messaging import project_delivery, send

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"
SUPP3 = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "supp3-20260914T160052Z"

NOW = "2026-09-24T10:00:00.000000+00:00"
SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
#: `03-after-stop.ansi` — an empty box, no dialog.
READY = (RUN / "03-after-stop.ansi").read_bytes()
#: `A2-typed-over-suggestion.ansi` — a real draft in the box.
DRAFT = (SUPP3 / "A2-typed-over-suggestion.ansi").read_bytes()
#: Never a substring of either capture, so counting it in `writes` is a real count.
BODY = "SHEPHERD-BC02-BODY"

#: How long a thread the fix must block is given to prove it is not blocked.
HELD_S = 2.0
#: The bound on every other join: a deadlock is a failure, never a hang.
JOIN_S = 5.0


def pane_state(raw: bytes) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(raw, parse_pane_fields(LIVE_FIELDS), [])


class GatedRunner:
    """`ScriptedRunner`, with the first caller of `gated` held on an `Event`.

    A delegating peer rather than a subclass (`ScriptedRunner` is inherited by
    nothing). `entered` says the first caller has arrived; `release` lets it go.
    Only the first is held: the other trigger's own call to the same member must
    pass, or a RED would be a timeout rather than the double write it names.
    """

    def __init__(self, inner: ScriptedRunner, gated: str) -> None:
        self.inner = inner
        self.gated = gated
        self.entered = threading.Event()
        self.release = threading.Event()
        self._first = threading.Lock()
        self._taken = False

    def _gate(self, member: str) -> None:
        if member != self.gated:
            return
        with self._first:
            first, self._taken = not self._taken, True
        if first:
            self.entered.set()
            assert self.release.wait(JOIN_S), "the gate was never released"

    def start(self, spec: SessionSpec) -> RunnerHandle:
        return self.inner.start(spec)

    def attach(self, handle: RunnerHandle) -> ByteStream:
        return self.inner.attach(handle)

    def snapshot(self, handle: RunnerHandle, scrollback: int) -> bytes:
        return self.inner.snapshot(handle, scrollback)

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        self.inner.write(handle, data)

    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None:
        self.inner.resize(handle, cols, rows)

    def interrupt(self, handle: RunnerHandle) -> None:
        self.inner.interrupt(handle)

    def terminate(self, handle: RunnerHandle) -> None:
        self.inner.terminate(handle)

    def probe(self, handle: RunnerHandle) -> ProcState:
        return self.inner.probe(handle)

    def pane(self, handle: RunnerHandle) -> PaneState:
        self._gate("pane")
        return self.inner.pane(handle)

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        return self.inner.list_owned_panes()

    def attached_clients(self, handle: RunnerHandle) -> int:
        self._gate("attached_clients")
        return self.inner.attached_clients(handle)

    def clear_input(self, handle: RunnerHandle) -> None:
        self.inner.clear_input(handle)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def scripted(panes: tuple[PaneState, ...]) -> tuple[ScriptedRunner, RunnerHandle]:
    """A fixture runner already holding the pane its handle names."""
    runner = ScriptedRunner(
        panes=panes,
        proc=ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW),
        screen=READY,
    )
    handle = runner.start(
        SessionSpec(
            session_id=SESSION_ID,
            engine_session_id="engine",
            cwd=str(REPO_ROOT),
            brief=None,
            title=None,
            model=None,
            effort=None,
            engine="stub",
            runner="scripted",
            env={},
        )
    )
    return runner, handle


def owned_row(store: Store, handle: RunnerHandle) -> None:
    """One owned, stopped row whose handle is the scripted pane's."""
    store.create_owned_session(
        session_id=SESSION_ID,
        engine_session_id=f"engine-{SESSION_ID}",
        workspace_id=store.create_project(name="shepherd", description=None).id,
        repo_id=None,
        cwd=str(REPO_ROOT),
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=handle,
        model=None,
        effort=None,
    )
    store.apply_fold_delta(SESSION_ID, FoldDelta(state=SessionState.STOPPED))


def queue_one(store: Store) -> None:
    queue_message(
        store=store,
        session_id=SESSION_ID,
        body=BODY,
        origin=MailboxOrigin.ORCHESTRATOR,
        idempotency_key="bc02",
        now=lambda: NOW,
    )


def body_writes(runner: ScriptedRunner) -> int:
    return sum(1 for data in runner.writes if BODY.encode("utf-8") in data)


def test_concurrent_deliveries_type_the_message_once(store: Store) -> None:
    """B2 / PP-B: two `deliver_now`s for one session type its message once.

    The first is held inside `pane()`, after it has read the pending set; the
    second runs meanwhile. **Goes red** as two body writes when the second is
    not held back until the first has finished.
    """
    inner, handle = scripted((pane_state(READY),))
    owned_row(store, handle)
    queue_one(store)
    runner = GatedRunner(inner, gated="pane")
    outcomes: dict[str, Delivery] = {}

    def attempt(label: str) -> None:
        outcomes[label] = deliver_now(
            store=store,
            runner=runner,
            handle=handle,
            session_id=SESSION_ID,
            state=SessionState.STOPPED,
            ownership=Ownership.OWNED,
            now=lambda: NOW,
        )

    first = threading.Thread(target=attempt, args=("first",))
    first.start()
    assert runner.entered.wait(JOIN_S), "the first delivery never reached the pane"
    second = threading.Thread(target=attempt, args=("second",))
    second.start()
    second.join(HELD_S)
    held = second.is_alive()
    runner.release.set()
    first.join(JOIN_S)
    second.join(JOIN_S)
    assert not first.is_alive() and not second.is_alive()

    # The message was typed once, with one submit…
    assert body_writes(inner) == 1, inner.writes
    assert inner.writes.count(b"\r") == 1, inner.writes
    # …by the held delivery, and the other attempt found nothing to send.
    assert outcomes["first"].delivered == 1
    assert outcomes["second"].delivered == 0
    assert held, "the second delivery was not held while the first was in flight"


def test_send_holds_the_queue_until_its_own_attempt(store: Store) -> None:
    """B2: the sweep cannot deliver between `send` queueing and `send` trying.

    `send` is held inside its first `attached_clients()`; the sweep's own
    `deliver_now` also calls it and passes ungated. **Goes red** as the sweep
    delivering the message (and `send` then typing it a second time).
    """
    inner, handle = scripted((pane_state(READY),))
    owned_row(store, handle)
    runner = GatedRunner(inner, gated="attached_clients")
    sent: dict[str, object] = {}
    swept: list[MailboxCounts] = []

    def route() -> None:
        args: dict[str, object] = {
            "session_id": SESSION_ID,
            "body": BODY,
            "idempotency_key": "bc02-route",
        }
        sent.update(send(store=store, runner=runner, now=lambda: NOW, args=args))

    def sweep() -> None:
        swept.append(
            sweep_pending(store=store, runner=runner, now=lambda: NOW, handles={SESSION_ID: handle})
        )

    sender = threading.Thread(target=route)
    sender.start()
    assert runner.entered.wait(JOIN_S), "send never reached its own attempt"
    sweeper = threading.Thread(target=sweep)
    sweeper.start()
    sweeper.join(HELD_S)
    held = sweeper.is_alive()
    early = list(swept)
    runner.release.set()
    sender.join(JOIN_S)
    sweeper.join(JOIN_S)
    assert not sender.is_alive() and not sweeper.is_alive()

    assert early == [], f"the sweep ran while send held the queue: {early}"
    assert held
    # Arrival: send's own attempt delivered…
    assert sent["delivered"] == 1
    assert sent["decision"] == "send_now"
    # …and the sweep, let through afterwards, delivered nothing.
    assert swept[0].delivered == 0
    assert body_writes(inner) == 1, inner.writes


def test_a_cleared_draft_is_reported_as_clear_then_send(store: Store) -> None:
    """B3 / PP-C: a draft the clear removed is `clear_then_send`, not `send_now`.

    The re-read decides `SEND_NOW` over the now-empty box, which is what was
    returned before BC-02 — a report that hides the clear from every reader.
    """
    inner, handle = scripted((pane_state(DRAFT), pane_state(READY)))
    owned_row(store, handle)
    queue_one(store)

    outcome = deliver_now(
        store=store,
        runner=inner,
        handle=handle,
        session_id=SESSION_ID,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: NOW,
    )

    # Arrival: the clear ran, and the message went.
    assert "clear_input" in inner.calls
    assert outcome.delivered == 1
    assert body_writes(inner) == 1
    assert outcome.decision is WriteDecision.CLEAR_THEN_SEND
    assert project_delivery(outcome, "m1")["decision"] == "clear_then_send"
