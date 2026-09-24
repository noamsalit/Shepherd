"""qa6 P5 / BC-08 — a turn that fails to open loses nothing and leaks nothing.

**The defect** (report §8, M18). `send_turn` drained the wake set *before*
`build_master` could fail, so a runtime that did not start consumed §12's
*"while you were away —"* summary and moved the stamp for a turn that never
ran; and both failure texts were `repr(error)` — an exception class name and
its message handed to a person (S8).

**The seam is `TurnDriver`'s public interface** over a real `Store` in
`tmp_path`, with `test_master_turn.py`'s own `RecordingMaster` double and
fixtures — imported rather than restated, so the two files cannot drift on what
a waking stop or a runtime double is.
"""

from __future__ import annotations

import pytest

from shepherd.core.master import MasterRuntime
from shepherd.orchestration.master_turn import (
    STREAM_KIND_PREFIX,
    TurnDriver,
    TurnRefused,
    TurnStarted,
)
from shepherd.orchestration.wake import MASTER_LAST_TURN_KEY, peek
from shepherd.store.db import Store

from .test_master_turn import (  # noqa: F401 — `recorder` and `store` are fixtures
    ARRIVAL_TIMEOUT_S,
    TURN_OPENED,
    WAKING_ID,
    Recorder,
    RecordingMaster,
    an_event,
    finish,
    plant_a_waking_stop,
    recorder,
    store,
)

#: A message only this file could have produced, so its absence from a reason
#: is the absence of *this* exception, not of a coincidental phrase.
BOOM = "QA6-P5-THE-RUNTIME-NEVER-STARTED"


def a_driver_whose_first_build_raises(
    store: Store, recorder: Recorder, *after: RecordingMaster
) -> TurnDriver:
    """The first turn's factory raises; every later turn gets the next double."""
    queue = list(after)
    calls: list[str] = []

    def build(turn_id: str) -> MasterRuntime:
        calls.append(turn_id)
        if len(calls) == 1:
            raise RuntimeError(BOOM)
        runtime: MasterRuntime = queue.pop(0)
        return runtime

    return TurnDriver(
        store=store,
        build_master=build,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: TURN_OPENED,
    )


def assert_no_internals(text: str) -> None:
    assert "RuntimeError" not in text, text
    assert f"({BOOM!r}" not in text and f"({BOOM}" not in text, text
    assert BOOM not in text, text


def test_a_turn_that_fails_to_open_keeps_the_wake_summary(
    store: Store, recorder: Recorder
) -> None:
    """Arrival first: the summary is asserted present before the failing send, so
    "it survived" cannot be satisfied by a summary that was never there."""
    plant_a_waking_stop(store)
    assert [item.session_id for item in peek(store)] == [WAKING_ID]

    after = RecordingMaster(events=(an_event("turn_ended"),))
    driver = a_driver_whose_first_build_raises(store, recorder, after)
    try:
        assert isinstance(driver.send_turn("the turn that cannot open"), TurnRefused)
        assert not driver.is_running(), "a failed open kept the slot"
        # Nothing was consumed and the stamp did not move for a turn that never ran.
        assert [item.session_id for item in peek(store)] == [WAKING_ID]
        assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

        assert isinstance(driver.send_turn("what happened?"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    assert len(after.sent) == 1
    assert after.sent[0].startswith("while you were away —"), after.sent[0][:200]
    assert after.sent[0].endswith("what happened?")


def test_no_failure_reason_carries_internals(store: Store, recorder: Recorder) -> None:
    """Both failure texts a person can see: the refusal when the runtime cannot be
    built, and the ring's `error` event when a running turn raises (S8)."""
    boom = RecordingMaster(raises=RuntimeError(BOOM))
    driver = a_driver_whose_first_build_raises(store, recorder, boom)
    try:
        refused = driver.send_turn("the turn that cannot open")
        assert isinstance(refused, TurnRefused)
        assert "could not be opened" in refused.reason, refused.reason
        assert_no_internals(refused.reason)

        assert isinstance(driver.send_turn("the turn that raises"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    errors = [e for e in recorder.published if e.kind == f"{STREAM_KIND_PREFIX}error"]
    assert len(errors) == 1, [e.kind for e in recorder.published]
    text = errors[0].payload["text"]
    assert isinstance(text, str) and text, errors[0].payload
    assert_no_internals(text)


def test_a_runtime_built_for_a_turn_that_fails_to_open_is_closed(
    store: Store, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime is now built before the drain, so a drain that fails must not
    leave that runtime open with no turn to close it."""
    built = RecordingMaster(events=(an_event("turn_ended"),))

    def the_store_is_gone(_key: str, _value: str) -> None:
        raise OSError("disk I/O error")

    monkeypatch.setattr(store, "set_app_state", the_store_is_gone)
    driver = TurnDriver(
        store=store,
        build_master=lambda _turn_id: built,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: TURN_OPENED,
    )
    assert isinstance(driver.send_turn("hello"), TurnRefused)
    assert not driver.is_running()
    assert built.sent == [], "a turn that failed to open still reached the runtime"
    assert built.closed == 1, "the runtime built for a refused turn was never closed"


class CloseRaises(RecordingMaster):
    """A runtime whose `close()` itself fails — the second failure in a row."""

    def close(self) -> None:
        super().close()
        raise RuntimeError("QA6-REMFIX-1-CLOSE-FAILED")


def test_a_close_that_raises_on_a_failed_open_still_releases_the_slot(
    store: Store, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REMFIX-1 #2 (hunter H2): the drain fails, then the runtime's `close()` fails.

    The open-failure path closed the runtime and *then* released the slot, so a
    raising `close()` skipped the release and every later turn was refused with
    "a turn is already running" for the life of the daemon. The release is now in
    a `finally`, `_run_turn`'s shape; the close's own error still surfaces.
    """
    built = CloseRaises(events=(an_event("turn_ended"),))
    after = RecordingMaster(events=(an_event("turn_ended"),))
    queue: list[RecordingMaster] = [built, after]
    real_set_app_state = store.set_app_state
    failing = {"on": True}

    def the_store_fails_once(key: str, value: str) -> None:
        if failing["on"]:
            failing["on"] = False
            raise OSError("disk I/O error")
        real_set_app_state(key, value)

    monkeypatch.setattr(store, "set_app_state", the_store_fails_once)
    driver = TurnDriver(
        store=store,
        build_master=lambda _turn_id: queue.pop(0),
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: TURN_OPENED,
    )
    try:
        with pytest.raises(RuntimeError, match="QA6-REMFIX-1-CLOSE-FAILED"):
            driver.send_turn("the turn that cannot open")
        assert built.closed == 1
        assert not driver.is_running(), "a raising close kept the slot"

        second = driver.send_turn("the next turn")
        assert isinstance(second, TurnStarted), second
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)
