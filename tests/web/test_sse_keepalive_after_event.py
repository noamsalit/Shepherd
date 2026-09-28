"""BC-33: the keep-alive follows one idle period, including one after an event.

Seam: `sse.stream`, with `sse.subscribe` replaced by a scripted generator. A
subscription only ends after `idle_timeout_s` of silence, so its end **is** an
idle period — whether or not it delivered first. The keep-alive used to be
written only after an *empty* subscription, which put the first comment after
an event two idle periods (about 30 s) later instead of one.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.stream import StreamDelivery
from shepherd.web import sse

AT = "2026-09-16T10:00:30Z"


def _delivery(seq: int) -> StreamDelivery:
    return StreamDelivery(
        seq=seq,
        event=StreamEvent(kind="session.state_changed", session_id="s-1",
                          payload={"to": "needs_you"}, occurred_at=AT),
    )


class ScriptedSubscriptions:
    """Each call is one subscription: the first delivers seq 1 then goes idle;
    every later one delivers the next seq, so a second subscription is visible."""

    def __init__(self) -> None:
        self.cursors: list[int | None] = []

    def __call__(
        self, since_seq: int | None, idle_timeout_s: float | None = None
    ) -> Iterator[StreamDelivery]:
        self.cursors.append(since_seq)
        yield _delivery(len(self.cursors))


@pytest.fixture()
def scripted(monkeypatch: pytest.MonkeyPatch) -> ScriptedSubscriptions:
    subscriptions = ScriptedSubscriptions()
    monkeypatch.setattr(sse, "subscribe", subscriptions)
    return subscriptions


def test_a_keepalive_follows_an_event_after_one_idle_period(
    scripted: ScriptedSubscriptions,
) -> None:
    produced = sse.stream(None, idle_timeout_s=0.01)
    items = [next(produced) for _ in range(3)]
    assert items == [sse.OPENED, sse.frame(sse.envelope(_delivery(1))), sse.KEEPALIVE]
    assert scripted.cursors == [None]


def test_the_cursor_still_resumes_after_the_event(scripted: ScriptedSubscriptions) -> None:
    """The cursor handling is unchanged: the next subscription starts at seq 1."""
    produced = sse.stream(None, idle_timeout_s=0.01)
    for _ in range(4):
        next(produced)
    assert scripted.cursors == [None, 1]
