"""S7 — shutdown with work in flight on a thread shutdown does not own.

§T25-8's production shape: `ThreadingHTTPServer` serves off threads that are
**not** in `Controld.threads`, so a worker released by shutdown's withdrawal can
come back to a store `shut_down` has already closed. Clause 20's promise is that
nobody is left **blocked**; what it does not promise is *which* of two answers
the released caller gets — D54's refusal, or a `RuntimeError` from a closed
store.

The shipped `tests/daemons/test_shutdown_master.py` records the hazard honestly
and asserts only `page_answer[0]["is_error"] is True` — which is **true in both
branches**: `client.call` answers an error mapping on a refusal, and the test's
own `except` writes the same key on a raise. So the shipped check cannot say
which one this tree actually does, and neither could anybody reading it.

**That is what this scenario adds.** The same shape, driven repeatedly, with the
two branches recorded *separately* and never folded into one another. What is
**asserted** is clause 20 alone — released, and released before the card's own
deadline. What is **measured** is the branch distribution, which goes into
`docs/plans/m1-m4-qa/harness.md`.

*The lying implementation this catches:* one that launders a raise into a
refusal — the two are counted apart, and the check fails if the recorded
outcomes are not one of the two shapes it knows about. Also one that "frees" the
worker by letting its 600 s deadline expire: the release instant is compared
against `deadline_at`, so a timeout reads as a timeout.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.core.clock import parse_stamp, utc_now
from shepherd.core.master import MasterRuntime
from shepherd.daemons import plane
from shepherd.daemons.shutdown import shut_down
from shepherd.store.db import Store, open_store
from shepherd.toolsurface import client, compose
from shepherd.toolsurface.approvals import Approval
from shepherd.toolsurface.registry import invoke, reset_registry
from shepherd.toolsurface.stream import reset_stream
from shepherd.toolsurface.types import Audience, CallerContext

from .conftest import scripted_host

TIMEOUT_S = 10.0

#: How many times the race is run. Not a flake-retry loop — **every** run is
#: asserted against clause 20, and the repetition exists to measure whether the
#: *branch* is stable. A single run cannot tell "always a refusal" from "usually
#: a refusal", and the difference is what §T25-8's three repair options turn on.
RUNS = 5

#: The two shapes a released caller can come back with. Written out, so an
#: outcome that is neither is a failure rather than an unnoticed third case.
REFUSED = "refused"
RAISED = "raised"


@dataclass
class Released:
    """What one released caller came back with, and when."""

    branch: str
    at: str
    detail: str


@dataclass
class Page:
    """A caller that is **not** one of the daemon's own threads (§T25-8).

    This stands in for `ThreadingHTTPServer`'s per-request thread: `shut_down`
    is handed an empty thread tuple, so this worker is outside the set it joins
    and outside the set it waits for — which is the whole of the hazard.
    """

    released: list[Released] = field(default_factory=list)

    def wait_on_a_card(self) -> None:
        try:
            answer = client.call(
                "kill_session", {"session_id": "other"}, "page", "s7-not-the-masters-turn"
            )
        except Exception as raised:  # noqa: BLE001 - the hazard, recorded as itself
            self.released.append(
                Released(branch=RAISED, at=utc_now(), detail=repr(raised))
            )
            return
        self.released.append(
            Released(branch=REFUSED, at=utc_now(), detail=repr(dict(answer)))
        )


class BlockedMaster:
    """A runtime whose turn makes one real gated call and parks on the card.

    `toolsurface.client.call` is the shipped path a master tool handler takes
    (`master/sdk_tools.py`), carrying the turn id `plane.build_master` hands the
    real runtime. So what parks here is a worker in front of a human-shaped
    gate, which is what clause 20 is about.
    """

    def __init__(self, turn_id: str, entered: threading.Event) -> None:
        self.turn_id = turn_id
        self.entered = entered
        self.released: list[Released] = []
        self.closed = 0

    def configure(self, tools: tuple[object, ...], system_prompt: str) -> None:
        pass

    def send(self, text: str) -> object:
        async def stream() -> object:
            self.entered.set()
            try:
                answer = client.call(
                    "kill_session", {"session_id": "no-such"}, "master", self.turn_id
                )
            except Exception as raised:  # noqa: BLE001 - recorded, never swallowed
                self.released.append(
                    Released(branch=RAISED, at=utc_now(), detail=repr(raised))
                )
            else:
                self.released.append(
                    Released(branch=REFUSED, at=utc_now(), detail=repr(dict(answer)))
                )
            if False:  # pragma: no cover - an async generator with no events
                yield None

        return stream()

    def resume(self, master_session_id: str) -> None:
        pass

    def interrupt(self) -> None:
        pass

    def capabilities(self) -> object:  # pragma: no cover
        raise AssertionError("no capability is read here")

    def close(self) -> None:
        self.closed += 1


@dataclass
class Composed:
    wiring: compose.M4Wiring
    store: Store
    masters: list[BlockedMaster]
    entered: threading.Event


def compose_one(tmp_path: Path, index: int) -> Composed:
    """One whole composed process, in its own directory."""
    root = tmp_path / f"run-{index}"
    host = scripted_host(root)
    db_path = root / "data" / "shepherd.db"
    store = open_store(db_path)
    masters: list[BlockedMaster] = []
    entered = threading.Event()

    def build(_store: Store, turn_id: str) -> MasterRuntime:
        master = BlockedMaster(turn_id, entered)
        masters.append(master)
        runtime: MasterRuntime = master
        return runtime

    wiring = compose.compose_tool_surface(
        store, host, db_path, host.control_socket("sessiond"), build, plane.audit_sink(store, host)
    )
    return Composed(wiring=wiring, store=store, masters=masters, entered=entered)


@pytest.fixture(autouse=True)
def clean_globals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """ADR-7's four module globals, reset on both sides of every run."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    yield
    compose.reset_master_plane()
    client.reset_master_client()
    reset_registry()
    reset_stream()


def wait_for_cards(world: Composed, count: int) -> tuple[Approval, ...]:
    """Block until `count` cards are pending, bounded. Arrival, not a sleep."""
    clock = threading.Event()
    for _ in range(int(TIMEOUT_S * 200)):
        pending = world.wiring.approvals.pending()
        if len(pending) >= count:
            return pending
        clock.wait(0.005)
    raise AssertionError(f"{count} approvals never arrived within {TIMEOUT_S}s")


def one_race(tmp_path: Path, index: int) -> tuple[Released, tuple[Approval, ...]]:
    """Open a turn, park a foreign worker beside it, shut down, read both back."""
    world = compose_one(tmp_path, index)
    page = Page()
    worker = threading.Thread(target=page.wait_on_a_card, name="s7-a-page", daemon=True)

    opened = invoke(
        "master_send",
        {"text": "do the destructive thing"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id=f"s7-{index}"),
    )
    assert opened.ok is True, opened.error
    assert world.entered.wait(TIMEOUT_S), "the turn never reached its tool call"
    worker.start()
    cards = wait_for_cards(world, 2)

    # Arrival: two distinct callers really are parked, on two distinct turns.
    assert len({card.turn_id for card in cards}) == 2, [card.turn_id for card in cards]

    # `shut_down((), …)` — an empty thread tuple is §T25-8's shape exactly: the
    # page's worker is not a thread this shutdown owns or joins.
    shut_down((), world.store.close, TIMEOUT_S)
    worker.join(TIMEOUT_S)

    assert not worker.is_alive(), "the foreign worker was never released"
    assert page.released, "the foreign worker never came back at all"
    assert world.wiring.approvals.pending() == (), "a card outlived the shutdown"
    compose.reset_master_plane()
    client.reset_master_client()
    reset_registry()
    reset_stream()
    return page.released[0], cards


def test_clause_20_holds_on_every_run_and_the_branch_is_recorded(
    tmp_path: Path,
) -> None:
    """The assertion is clause 20; the branch is a measurement.

    Nobody is left blocked, and the release is a **release** rather than a
    deadline — the card's own `deadline_at` is still in the future at the moment
    the worker came back, which is the only way to tell our compare-and-set from
    the 600 s timeout (P2 measured that no cancellation reaches a running
    handler, so a wrong key would still look green without this).

    The branch each run took is recorded and compared against the two shapes
    this file knows about. A third shape — a worker that returned `ok=True`, a
    release with no answer at all — fails, rather than being counted as a
    refusal.
    """
    outcomes: list[Released] = []
    for index in range(RUNS):
        released, cards = one_race(tmp_path, index)
        outcomes.append(released)

        moment = parse_stamp(released.at)
        deadline = parse_stamp(cards[0].deadline_at)
        assert moment is not None and deadline is not None
        assert moment < deadline, (
            f"run {index}: the worker came back at {released.at}, at or past the"
            f" card's own deadline {cards[0].deadline_at} — that is a timeout,"
            " not a release"
        )

    assert len(outcomes) == RUNS
    branches = {released.branch for released in outcomes}
    report = ", ".join(
        f"{branch}×{sum(1 for o in outcomes if o.branch == branch)}"
        for branch in sorted(branches)
    )
    assert branches <= {REFUSED, RAISED}, sorted(branches)

    # **Measured, not assumed: this is not a rare race.** 20 of 20 runs of
    # `one_race` took the same branch on this host, and it is the *unhappy* one —
    # the released caller comes back with `RuntimeError("store is closed")`
    # rather than D54's refusal, every time. §T25-8 calls it a race a worker
    # "can" lose; on this tree it loses always.
    #
    # Written as an equality so the **repair** is visible: whichever of T25's
    # three options lands (a grace period, an in-flight-waiter reader, or
    # swallowing the exception — the third being the one this repo refuses), the
    # branch flips and this check says so. An `in {REFUSED, RAISED}` here would
    # have stayed green through the fix and through a regression alike.
    assert branches == {RAISED}, (
        f"the released caller no longer always raises ({report}) — §T25-8 may be"
        " repaired, or the hazard has become intermittent; both are findings"
    )


def test_the_recorder_can_produce_both_branches(tmp_path: Path) -> None:
    """The control: this file's recorder really can tell the two apart.

    One of each, produced deliberately with the **same** recorder and the same
    call — a real refusal (a withdrawal, nothing shut down) and a real raise (the
    same call against a store that has been closed underneath it). Without this,
    a run that recorded `refused` five times out of five would be indistinguishable
    from a recorder whose `except` branch is unreachable, and the measurement in
    `test_clause_20_holds_on_every_run_and_the_branch_is_recorded` would be about
    this file rather than about the product.
    """
    world = compose_one(tmp_path, 99)
    refused = Page()
    worker = threading.Thread(target=refused.wait_on_a_card, name="s7-refusal", daemon=True)
    worker.start()
    cards = wait_for_cards(world, 1)
    assert world.wiring.approvals.withdraw(cards[0].id) is True
    worker.join(TIMEOUT_S)
    assert not worker.is_alive()
    assert refused.released[0].branch == REFUSED, refused.released[0]

    # The other branch, from the same recorder: the gate reads the autonomy
    # level off the store, so a closed store raises out of `invoke` itself.
    world.store.close()
    raised = Page()
    raised.wait_on_a_card()
    assert raised.released[0].branch == RAISED, raised.released[0]
    assert refused.released[0].branch != raised.released[0].branch


def test_the_shipped_check_cannot_tell_the_branches_apart(tmp_path: Path) -> None:
    """Why S7 exists, asserted rather than asserted-about.

    `is_error` is `True` on both sides, so the shipped predicate is satisfied by
    either branch. Driven on a real refusal: the exact expression the shipped
    check uses is shown to be true of the branch it was **not** written to
    describe, which is what makes it an under-determined check rather than a
    wrong one.
    """
    world = compose_one(tmp_path, 98)
    page = Page()
    worker = threading.Thread(target=page.wait_on_a_card, name="s7-shape", daemon=True)
    worker.start()
    cards = wait_for_cards(world, 1)
    assert world.wiring.approvals.withdraw(cards[0].id) is True
    worker.join(TIMEOUT_S)
    assert not worker.is_alive()

    released = page.released[0]
    assert released.branch == REFUSED
    # The refusal's own mapping carries `is_error: True` — the shipped
    # assertion's exact predicate, satisfied by a refusal.
    assert "'is_error': True" in released.detail, released.detail
