"""T27 — the master turn driver: one turn at a time, one loop per turn.

**The component that runs a turn** (ADR-M4-10). Revision 1 of the M4 plan had
three tasks consuming `send_turn`/`interrupt_master`, a chat page rendering what
this module publishes, and an acceptance clause asserting its behaviour — and no
task producing it. A hole that shape gets filled by a builder improvising inside
the composition root, so **P-M4-21 asserts by AST that `MasterRuntime.send()`
has exactly one caller in `src/`**, and this module is it.

**What one turn is, in order, because the order is the contract:**

1. **Take the slot or refuse** (RD7). A second `send_turn` while one is live is
   refused *readably* and is **not queued**: §12's chat is turn-based, and a
   queue needs an ordering policy nobody has specified.
2. **Open with the wake summary.** The turn opens with D31's drained set
   rendered by `wake.render_wake_text` and the user's text beneath it, and the
   drain moves `master_last_turn_at` (§12's *"while you were away —"*).
3. **One worker thread, one `asyncio.run()`.** `MasterRuntime.send()` is an
   `AsyncIterator` exactly as §6:472 writes it (DP12), so somebody must own a
   loop. It is this module, **per turn**, and the loop dies with the turn: this
   build starts no loop and no thread at boot.
4. **Project and publish.** Every `MasterEvent` becomes a `StreamEvent` through
   the injected `publish`, onto the ring the chat page and the sidebar already
   read (ADR-M4-7).
5. **Persist `master_session_id`** from the first event of the turn that carries
   one, so D10's one continuous orchestrator conversation survives a restart.
6. **Release the slot on every exit path, including an exception.** A slot
   released only on success is a chat that wedges on the first error.

**`interrupt_master()` withdraws first, then interrupts** (ADR-M4-3, measured by
probe P2). No cancellation of any kind reaches a running in-process tool handler
— not deferred, never delivered — so the *only* thing that can free a worker
blocked in `await_decision` is our own store's compare-and-set. Reversing the two
leaves that worker blocked until the 600 s timeout, which is the defect DP5's
re-derivation exists to close, and **P-M4-22** is the check that proves the
release beat the deadline.

**Why `publish` and the withdrawal are injected rather than imported.** This is
L3. `toolsurface/` is L4, and L3 may not import upward (§5.0) — so the two L4
callables arrive as parameters, exactly as M3's composition root hands
`orchestration/` the publisher that `signals/` returned. The same rule is why no
vendor word appears here: `MasterEvent` in, `StreamEvent` out (K13, D32).

**One stamp, not two.** Flow A step 8 reads *"the driver stamps and releases"*,
and this module stamps **once, when the turn opens**. A second stamp at turn end
would mark every stop that happened *during* the turn as already seen and it
would never wake anything about them again — which is precisely the lost stop
`wake.drain`'s own docstring is built to prevent. Recorded as §T27-3.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from shepherd.core.ids import new_ulid
from shepherd.core.master import MasterEvent, MasterRuntime
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.wake import drain, render_wake_text
from shepherd.store.db import Store

__all__ = [
    "MASTER_SESSION_KEY",
    "STREAM_KIND_PREFIX",
    "TurnDriver",
    "TurnRefused",
    "TurnStarted",
    "project_to_stream",
]

#: §7's `app_state` key holding the runtime's own conversation id (D10). Read
#: off the event's payload under the **same** spelling: a runtime reports its
#: session the way it reports everything else, and a second name for one fact is
#: a fact two components can disagree about.
MASTER_SESSION_KEY = "master_session_id"

#: Every `StreamEvent` this module publishes is `master.<kind>` — the chat page
#: subscribes to the prefix and iterates `MASTER_EVENT_KINDS` for the rest, so
#: the kinds are never written out anywhere (K19).
STREAM_KIND_PREFIX = "master."

#: How long `close()` waits for a turn's thread before giving up on it. A
#: shutdown that blocks forever on a wedged runtime is worse than one that says
#: the thread outlived it; the thread is a daemon, so it never holds the process.
CLOSE_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class TurnRefused:
    """RD7's refusal. `reason` is shown to a person, so it is a sentence."""

    reason: str


@dataclass(frozen=True)
class TurnStarted:
    """The turn is running on its own thread; events arrive on the ring."""

    turn_id: str
    started_at: str


@dataclass
class _Turn:
    """The one turn in flight, and everything needed to end it."""

    turn_id: str
    started_at: str
    done: threading.Event = field(default_factory=threading.Event)
    runtime: MasterRuntime | None = None
    thread: threading.Thread | None = None
    session_recorded: bool = False


def project_to_stream(event: MasterEvent, turn_id: str) -> StreamEvent:
    """One `MasterEvent`, in the ring's words.

    The runtime's own `payload` is nested under `detail` rather than merged:
    merged, an event carrying a `turn_id` key of its own would overwrite the
    turn this event belongs to, and the page would attribute output to the
    wrong conversation.
    """
    return StreamEvent(
        kind=f"{STREAM_KIND_PREFIX}{event.kind}",
        session_id=None,
        payload={
            "turn_id": turn_id,
            "text": event.text,
            "tool_name": event.tool_name,
            "detail": dict(event.payload),
        },
        occurred_at=event.occurred_at,
    )


class TurnDriver:
    """The single caller of `MasterRuntime.send()` (P-M4-21).

    Everything below the seam is injected: the store, the runtime factory, the
    publisher, the withdrawal and the clock. Nothing is constructed at boot —
    `build_master` is called **per turn**, so a driver that has never run a turn
    has no runtime, no thread and no loop.

    **`build_master` is handed the turn's id** (RD-T4-2, §T20-1, §T21-1). The
    runtime keys every approval it raises on the turn it is running inside, and
    this driver withdraws by *its* id — so a runtime that minted its own would
    produce a key matching nothing, every blocked tool worker would ride its
    full 600 s deadline, and every test in this tree would stay green. P2
    measured that `interrupt()` frees no running handler, so the withdrawal is
    the only release mechanism there is and the key has to be right. The id is
    an **argument** rather than a `current_turn_id()` reader for the reason
    §T21-1 gives: a reader answers `str | None`, and every caller then has to
    invent a string for the `None` case — the wrong key again, arriving through
    the repair.
    """

    def __init__(
        self,
        *,
        store: Store,
        build_master: Callable[[str], MasterRuntime],
        publish: Callable[[StreamEvent], int],
        withdraw_turn_approvals: Callable[[str], int],
        now: Callable[[], str],
    ) -> None:
        self._store = store
        self._build_master = build_master
        self._publish = publish
        self._withdraw = withdraw_turn_approvals
        self._now = now
        self._lock = threading.Lock()
        self._turn: _Turn | None = None

    # ----- the public verbs, verbatim what T23's `ToolDef`s sit over ----------

    def send_turn(self, text: str) -> TurnStarted | TurnRefused:
        """Open one turn, or say readably why not.

        The slot is claimed **before** anything slow happens — the drain, the
        runtime, the thread — so two callers racing here cannot both open a
        turn, and a failure in any of the three releases it again.
        """
        with self._lock:
            if self._turn is not None:
                return TurnRefused(
                    reason=(
                        f"a turn is already running ({self._turn.turn_id}), and a"
                        " second turn is refused rather than queued — wait for it"
                        " to end, or interrupt it"
                    )
                )
            turn = _Turn(turn_id=new_ulid(), started_at=self._now())
            self._turn = turn

        try:
            prompt = self._opening_text(text)
            turn.runtime = self._build_master(turn.turn_id)
            turn.thread = threading.Thread(
                target=self._run_turn,
                args=(turn, turn.runtime, prompt),
                name=f"master-turn-{turn.turn_id}",
                daemon=True,
            )
            turn.thread.start()
        except Exception as error:
            self._release(turn)
            return TurnRefused(
                reason=f"the turn {turn.turn_id} could not be opened: {error!r}"
            )
        return TurnStarted(turn_id=turn.turn_id, started_at=turn.started_at)

    def interrupt_master(self) -> bool:
        """ADR-M4-3: withdraw, **then** interrupt. `False` when nothing is live.

        The withdrawal comes first because P2 measured that `interrupt()` frees
        no running handler: a worker blocked on an approval is released by our
        own store or by nothing at all until its 600 s deadline.
        """
        with self._lock:
            turn = self._turn
            runtime = turn.runtime if turn is not None else None
        if turn is None or runtime is None:
            return False
        self._withdraw(turn.turn_id)
        runtime.interrupt()
        return True

    def wait_for_turn(self, timeout_s: float) -> bool:
        """Block until the turn in flight has ended and its thread is gone.

        Not in the plan's Produces block, and it is here because a caller that
        cannot observe the end of a turn can only observe it by sleeping — which
        is the sampling this module's own checks refuse (§T27-2). `close()` and
        the checks both use it; `True` means the turn really ended.
        """
        with self._lock:
            turn = self._turn
        if turn is None:
            return True
        ended = turn.done.wait(timeout_s)
        if turn.thread is not None:
            turn.thread.join(timeout_s)
            return ended and not turn.thread.is_alive()
        return ended

    def is_running(self) -> bool:
        """Is the slot held?"""
        with self._lock:
            return self._turn is not None

    def close(self) -> None:
        """End the turn in flight and wait for its thread. Idempotent."""
        if self.is_running():
            self.interrupt_master()
            self.wait_for_turn(CLOSE_TIMEOUT_S)

    # ----- the turn itself ----------------------------------------------------

    def _opening_text(self, text: str) -> str:
        """§12's *"while you were away —"*, and the user's text beneath it.

        The drain both consumes the set and moves the stamp, and it returns the
        rows it consumed — so the summary is built from what this turn took,
        never re-read after the stamp moved. An empty set renders the empty
        string and prepends nothing at all, not a blank line.
        """
        opening = render_wake_text(drain(self._store, self._now))
        return f"{opening}\n\n{text}" if opening else text

    def _run_turn(self, turn: _Turn, runtime: MasterRuntime, prompt: str) -> None:
        """The worker: one thread, one `asyncio.run()`, torn down with the turn.

        An exception from the runtime becomes an `error` event on the ring — a
        turn that ended badly is still a turn, and a page told nothing cannot
        tell a failure from silence (principle 5).
        """
        try:
            asyncio.run(self._stream(turn, runtime, prompt))
        except Exception as error:
            self._publish(
                project_to_stream(
                    MasterEvent(
                        kind="error",
                        text=repr(error),
                        tool_name=None,
                        payload={"turn_id": turn.turn_id},
                        occurred_at=self._now(),
                    ),
                    turn.turn_id,
                )
            )
        finally:
            try:
                runtime.close()
            finally:
                self._release(turn)

    async def _stream(self, turn: _Turn, runtime: MasterRuntime, prompt: str) -> None:
        """The one `send()` call in `src/` (P-M4-21)."""
        async for event in runtime.send(prompt):
            self._remember_session(turn, event)
            self._publish(project_to_stream(event, turn.turn_id))

    def _remember_session(self, turn: _Turn, event: MasterEvent) -> None:
        """D10: the first event of the turn that names a session wins.

        First rather than last, because a later event restating a different id
        would move the conversation the next restart resumes.
        """
        if turn.session_recorded:
            return
        value = event.payload.get(MASTER_SESSION_KEY)
        if isinstance(value, str) and value:
            turn.session_recorded = True
            self._store.set_app_state(MASTER_SESSION_KEY, value)

    def _release(self, turn: _Turn) -> None:
        """Give the slot back, then say the turn is over — in that order.

        `done` is set **after** the slot is cleared, so a caller woken by it
        cannot observe a driver that has ended its turn and still holds the slot.
        """
        with self._lock:
            if self._turn is turn:
                self._turn = None
        turn.done.set()
