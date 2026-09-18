"""Clause 20 — shutdown closes the master and leaves nobody blocked on a card.

**Driven through the shipped `shut_down`**, with the shipped composition behind
it: `daemons/shutdown.py` is where ADR-M4-6 puts the close-and-withdraw step,
because it is not a composition root and `controld.py` is at 140 of the 140
lines ADR-1 leaves it. So the thing under test is the function `controld.stop()`
already calls, with no argument added to it.

**Arrival before absence, and the arrival is a synchronisation.** A turn is
asserted *running* and a card asserted *pending* before anything is shut down;
`Thread.is_alive()` is never sampled to mean "the work began".

**Every wait is bounded.** A mutant that hangs is not a red — two M4 tasks paid
for learning that — and the bound here is ten seconds against an approval
deadline of six hundred, which is exactly the gap
`test_the_withdrawal_beats_the_deadline_rather_than_waiting_for_it` reads.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from shepherd.core.clock import parse_stamp, utc_now
from shepherd.core.master import MasterRuntime
from shepherd.daemons import plane
from shepherd.daemons.shutdown import shut_down
from shepherd.host.base import HostPlatform
from shepherd.store.db import Store, open_store
from shepherd.toolsurface import client, compose
from shepherd.toolsurface.approvals import Approval

from scripted_hosts import build_scripted_host

TIMEOUT_S = 10.0
TURN_THREAD_PREFIX = "master-turn-"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture(autouse=True)
def clean_globals() -> Iterator[None]:
    """The registry, the ring, the client and the plane are module-global by
    ADR-7: every check starts and ends with none of them installed."""
    from shepherd.toolsurface.registry import reset_registry
    from shepherd.toolsurface.stream import reset_stream

    yield
    compose.reset_master_plane()
    client.reset_master_client()
    reset_registry()
    reset_stream()


class BlockedMaster:
    """A runtime whose turn makes one real gated call and parks on the card.

    The call is `toolsurface.client.call` — the **shipped** path the master's
    tool handlers take (`master/sdk_tools.py`) — carrying the turn id it was
    built for, exactly as `plane.build_master` hands it to `AgentSDKMaster`. So
    what parks here is a worker in front of a human-shaped gate, which is the
    thing clause 20 is about.
    """

    def __init__(self, turn_id: str, entered: threading.Event) -> None:
        self.turn_id = turn_id
        self.entered = entered
        self.answer: Mapping[str, object] | None = None
        self.released_at: str | None = None
        self.closed = 0
        self.interrupts = 0

    def configure(self, tools: tuple[object, ...], system_prompt: str) -> None:
        pass

    def send(self, text: str) -> object:
        async def stream() -> object:
            self.entered.set()
            self.answer = client.call(
                "kill_session", {"session_id": "no-such"}, "master", self.turn_id
            )
            self.released_at = utc_now()
            if False:  # pragma: no cover - an async generator with no events
                yield None

        return stream()

    def resume(self, master_session_id: str) -> None:
        pass

    def interrupt(self) -> None:
        self.interrupts += 1

    def capabilities(self) -> object:  # pragma: no cover
        raise AssertionError("no capability is read here")

    def close(self) -> None:
        self.closed += 1


class Composed:
    """One composed process, with the turn it is running."""

    def __init__(self, store: Store, host: HostPlatform, tmp_path: Path) -> None:
        self.masters: list[BlockedMaster] = []
        self.entered = threading.Event()
        self.host = host
        self.store = store

        def build(_store: Store, turn_id: str) -> MasterRuntime:
            master = BlockedMaster(turn_id, self.entered)
            self.masters.append(master)
            runtime: MasterRuntime = master
            return runtime

        self.wiring = compose.compose_tool_surface(
            store,
            host,
            tmp_path / "data" / "shepherd.db",
            host.control_socket("sessiond"),
            build,
            plane.audit_sink(store, host),
        )

    @property
    def master(self) -> BlockedMaster:
        assert self.masters, "no turn was ever opened"
        return self.masters[0]


@pytest.fixture()
def composed(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Composed:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    return Composed(store, build_scripted_host(tmp_path), tmp_path)


def wait_for_cards(world: Composed, count: int) -> tuple[Approval, ...]:
    """Block until `count` cards are pending, bounded. Arrival, not a sleep."""
    clock = threading.Event()
    for _ in range(int(TIMEOUT_S * 200)):
        pending = world.wiring.approvals.pending()
        if len(pending) >= count:
            return pending
        clock.wait(0.005)
    raise AssertionError(f"{count} approvals never arrived within {TIMEOUT_S}s")


def turn_threads() -> set[str]:
    return {
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith(TURN_THREAD_PREFIX)
    }


# ----- clause 20 --------------------------------------------------------------


def test_shutdown_closes_the_master_and_withdraws(composed: Composed) -> None:
    """The clause, whole: the turn is running and a card is pending; then the
    shipped `shut_down`; then the runtime is closed and the card is withdrawn.

    **Goes red if `close()` is never called** and **goes red if a worker is left
    blocked** — which the first revision of this wiring had no check for at all.
    """
    started = composed.wiring  # the composition is what raises the card
    assert started.approvals.pending() == ()

    from shepherd.toolsurface.registry import invoke
    from shepherd.toolsurface.types import Audience, CallerContext

    opened = invoke(
        "master_send",
        {"text": "do the destructive thing"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-1"),
    )
    assert opened.ok is True
    assert composed.entered.wait(TIMEOUT_S), "the turn never reached its tool call"
    card = wait_for_cards(composed, 1)[0]

    # Arrival, asserted rather than assumed: a turn is live and a person is
    # being asked something.
    assert card.tool == "kill_session"
    assert card.turn_id == composed.master.turn_id

    outcome = shut_down((), composed.store.close, TIMEOUT_S)

    assert outcome.store_closed is True
    assert composed.master.closed == 1, "shutdown never closed the runtime"
    assert composed.wiring.approvals.pending() == ()
    answer = composed.master.answer
    assert answer is not None, "the blocked call never came back"
    assert answer["is_error"] is True


def test_no_thread_is_left_blocked_on_an_approval(composed: Composed) -> None:
    """The second half, and the one the first revision could not see.

    Two callers park on cards — the turn's own, and a second one that is not the
    master's at all (§12's rail, a page, the CLI). Shutdown has to free **both**:
    `interrupt_master()` withdraws only the turn it is ending, and a worker left
    in front of anything else would wait its full 600 s for a process that is
    one line from gone.

    The thread set is compared before and after, and the turn's thread is
    asserted **present** first, so the emptiness afterwards is a change this
    shutdown made.

    **What the page's worker records, and why it is not just its answer.** The
    call is released by the withdrawal and then has one more thing to do: the
    authorizer counts `APPROVAL_WITHDRAWN` against the store — which `shut_down`
    closes as soon as the threads *it* owns have joined. A worker that is not one
    of those three can therefore lose the race and come back with
    `RuntimeError("store is closed")` instead of a refusal. That is a real
    ordering hazard in the shipped path, it is recorded in
    `docs/plans/m4-blockers/t25.md`, and this check does **not** launder it: what
    clause 20 promises is that nobody is left *blocked*, so the released moment
    is recorded by the worker itself before anything else can interfere, and the
    outcome it came back with — answer or raise — is recorded beside it.
    """
    before = turn_threads()
    from shepherd.toolsurface.registry import invoke
    from shepherd.toolsurface.types import Audience, CallerContext

    page_answer: list[Mapping[str, object]] = []
    page_released: list[str] = []

    def a_page_waiting() -> None:
        try:
            answer = client.call(
                "kill_session", {"session_id": "other"}, "page", "request-9"
            )
        except Exception as raised:  # noqa: BLE001 - the hazard above, recorded
            page_released.append(utc_now())
            page_answer.append({"is_error": True, "raised": repr(raised)})
            return
        page_released.append(utc_now())
        page_answer.append(answer)

    page = threading.Thread(target=a_page_waiting, name="a-page-waiting", daemon=True)

    invoke(
        "master_send",
        {"text": "go"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-2"),
    )
    assert composed.entered.wait(TIMEOUT_S)
    page.start()
    cards = wait_for_cards(composed, 2)

    # Arrival: two distinct cards, from two distinct callers, and the turn's
    # own worker thread really is running.
    assert len({card.turn_id for card in cards}) == 2
    assert turn_threads() - before, "no turn thread was ever started"

    shut_down((), composed.store.close, TIMEOUT_S)
    page.join(TIMEOUT_S)

    assert not page.is_alive(), "the page's call was never released"
    assert page_released, "the page's worker never came back at all"
    assert page_answer[0]["is_error"] is True
    # …and it was released rather than timed out: the card's own deadline is
    # still in the future at the moment the worker came back.
    released, deadline = parse_stamp(page_released[0]), parse_stamp(cards[0].deadline_at)
    assert released is not None and deadline is not None and released < deadline
    assert composed.wiring.approvals.pending() == ()
    assert turn_threads() - before == set(), "a turn thread outlived the shutdown"


def test_the_withdrawal_beats_the_deadline_rather_than_waiting_for_it(
    composed: Composed,
) -> None:
    """P-M4-22's shape at shutdown: the release is **not** a deadline.

    P2 measured that no cancellation reaches a running in-process tool handler,
    so a key that matched nothing would still look green here — the call would
    come back, ten minutes later, timed out. This asserts the card's own
    `deadline_at` is still in the future at the moment the worker was released,
    which a timeout cannot satisfy.
    """
    from shepherd.toolsurface.registry import invoke
    from shepherd.toolsurface.types import Audience, CallerContext

    invoke(
        "master_send",
        {"text": "go"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-3"),
    )
    assert composed.entered.wait(TIMEOUT_S)
    card = wait_for_cards(composed, 1)[0]

    shut_down((), composed.store.close, TIMEOUT_S)

    released_at = composed.master.released_at
    assert released_at is not None, "the worker was never released"
    released = parse_stamp(released_at)
    deadline = parse_stamp(card.deadline_at)
    assert released is not None and deadline is not None
    assert released < deadline, (
        f"the worker came back at {released_at}, at or past its own deadline"
        f" {card.deadline_at} — that is a timeout, not a release"
    )


def test_a_process_that_never_composed_still_shuts_down(store: Store) -> None:
    """`shut_down` is called by `controld.stop()` unconditionally, and a test
    daemon, a refused start and `shepherd status` never compose a master. The
    close-and-withdraw step therefore has to be a no-op rather than a raise."""
    assert compose.master_plane() is None

    outcome = shut_down((), store.close, TIMEOUT_S)

    assert outcome.store_closed is True
    assert outcome.hung == ()
