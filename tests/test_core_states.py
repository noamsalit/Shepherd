"""T1: fleet ordering vocabulary (§16 — M1 has three live states)."""

from shepherd.core.states import FLEET_STATE_ORDER, Origin, Ownership, SessionState


def test_fleet_state_order_matches_spec() -> None:
    # §16: "needs_you -> running -> stopped".
    position = {state: index for index, state in enumerate(FLEET_STATE_ORDER)}
    assert position[SessionState.NEEDS_YOU] < position[SessionState.RUNNING]
    assert position[SessionState.RUNNING] < position[SessionState.STOPPED]

    # Total, so a sort key can never fall off the end of the table.
    assert len(FLEET_STATE_ORDER) == len(set(FLEET_STATE_ORDER)) == len(SessionState)
    assert set(FLEET_STATE_ORDER) == set(SessionState)

    # The wire values are the spec's, not the member names.
    assert [state.value for state in SessionState] == [
        "starting",
        "running",
        "needs_you",
        "stopped",
    ]
    assert [o.value for o in Ownership] == ["owned", "attached"]
    assert [o.value for o in Origin] == [
        "orchestrator",
        "queue_worker",
        "user_ui",
        "external",
        "ask_fork",
    ]
