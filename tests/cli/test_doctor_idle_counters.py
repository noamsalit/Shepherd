"""T18-2's honesty debt, PAID by M3 Task 22 — the two counters can now move.

M1's `TOOL_BLOCKED_BY_HOOK` and `TOOL_PERMISSION_REFUSED` were built from 40 real
captures and, for two milestones, **could never fire**: the only hook event that
records a permission refusal or a hook block was not in `SUBSCRIBED_EVENTS`, so
nothing dispatched it, nothing folded it, and `doctor` printed `idle` with the
reason rather than a `0` that would have claimed coverage this build never had.

M3 Task 22 executed M1's preserved checklist — the name is subscribed, the
installer's dry-run diff was re-reviewed against a **populated throwaway**
settings file (`tests/engines/test_post_tool_batch_subscription.py`), the
`hookd` latency probe was re-run against E34's budget, and the real
`~/.claude/settings.json` is byte-identical. So the `idle` line is gone, and
these two render as the counts they now are.

**What replaced what, so the deletion is legible rather than silent:**

* `test_post_tool_batch_is_still_not_subscribed` →
  `tests/engines/test_post_tool_batch_subscription.py::test_post_tool_batch_is_subscribed`,
  which names this task and fails if the name is removed again;
* `test_doctor_reports_the_refusal_counters_as_idle_not_zero` →
  `test_doctor_reports_the_refusal_counters_as_counts` below, which fails if the
  `idle` rendering comes back **or** if a counter that moved is printed as
  anything but its number.

A `0` from these two is now honest: this build **does** look. It looks because
`test_the_two_refusal_counters_can_now_move` drives a real captured
`PostToolBatch` refusal through the production lane and watches one increment —
the only thing that makes this task worth doing.

Seam: `main(argv)` → `invoke()`, the same seam as the rest of `tests/cli/`, and
`HookLane.apply` for the lane that feeds it.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from cli.conftest import register_tools, scripted_host
from golden.corpus import CorpusEvent, load_corpus

from shepherd.cli import commands
from shepherd.cli.main import EXIT_OK, main
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.frames import Frame
from shepherd.engines.claude_code.events import SUBSCRIBED_EVENTS
from shepherd.signals.fields import read_refusal
from shepherd.signals.hook_lane import HookLane
from shepherd.engines.claude_code.normalise import parse_hook_payload
from shepherd.store.db import Store

#: The one event that carries a refusal, named **here in the test** and nowhere
#: in `src/` outside `engines/`: §5.0's engine-vocabulary rule fails the build on
#: a hook event name in a literal anywhere else, and it is not scanned over
#: `tests/`.
REFUSAL_EVENT = "PostToolBatch"

REFUSAL_COUNTERS = (
    AnomalyKind.TOOL_BLOCKED_BY_HOOK.value,
    AnomalyKind.TOOL_PERMISSION_REFUSED.value,
)

#: The neutral `refusal` values (BLOCKER T11-2) → the counter each one bumps.
#: Both have a real captured example in the corpus; the parametrised case count
#: is asserted below so an empty table cannot pass as a green.
REFUSAL_CASES: tuple[tuple[str, str], ...] = (
    ("permission", AnomalyKind.TOOL_PERMISSION_REFUSED.value),
    ("hook_block", AnomalyKind.TOOL_BLOCKED_BY_HOOK.value),
)


def captured_refusals() -> dict[str, CorpusEvent]:
    """One real captured envelope per refusal value, from the 429 (K1).

    `refusal` is read through the **production** reader, so a fixture that no
    longer produces a refusal cannot silently be selected.
    """
    found: dict[str, CorpusEvent] = {}
    for event in load_corpus():
        if event.event != REFUSAL_EVENT:
            continue
        parsed = parse_hook_payload(event.raw, event.received_at)
        refusal = None if isinstance(parsed, str) else read_refusal(parsed)  # type: ignore[arg-type]
        if isinstance(refusal, str) and refusal not in found:
            found[refusal] = event
    return found


def anomalies_block(printed: str) -> str:
    """The `anomalies:` line and any indented continuation that belongs to it."""
    lines = printed.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("anomalies:"))
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith(" "):
            break
        block.append(line)
    return "\n".join(block)


def test_both_refusal_values_have_a_real_captured_example() -> None:
    """The case count, asserted. A parametrised loop over an empty table is a
    green that observed nothing — this repo's dominant defect in its cheapest
    form."""
    assert len(REFUSAL_CASES) == 2
    assert set(captured_refusals()) == {value for value, _ in REFUSAL_CASES}


@pytest.mark.parametrize(("refusal", "counter"), REFUSAL_CASES)
def test_the_two_refusal_counters_can_now_move(
    store: Store, refusal: str, counter: str
) -> None:
    """The point of Task 22: drive a real `PostToolBatch` frame, watch it move.

    Goes red if the counters are still structurally dead. Arrival is asserted
    before absence — the counter is read at zero first, so a fixture that never
    reached the lane cannot pass by leaving it unset.
    """
    captured = captured_refusals()[refusal]
    # **The load-bearing line.** The fold has always known how to count this
    # frame; what was dead was the delivery — nothing dispatched the event,
    # because the installer only writes entries for `SUBSCRIBED_EVENTS`. Without
    # this assertion the test passes against M1's build and proves nothing.
    # That the name actually reaches a settings file is asserted end-to-end in
    # `tests/engines/test_post_tool_batch_subscription.py`.
    assert captured.event in SUBSCRIBED_EVENTS, (
        "nothing dispatches this event, so the counter below is still dead"
    )
    assert store.list_anomaly_counts().get(counter, 0) == 0

    HookLane(store, lambda event: 0).apply(
        Frame(payload=captured.raw, received_at=captured.received_at, peer_pid=None)
    )

    counts = store.list_anomaly_counts()
    assert counts[counter] == 1, counts
    # …and only the one it should: two counters that move together are one
    # counter with two names.
    other = next(name for name in REFUSAL_COUNTERS if name != counter)
    assert counts.get(other, 0) == 0, counts


def test_doctor_reports_the_refusal_counters_as_counts(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Replaces `test_doctor_reports_the_refusal_counters_as_idle_not_zero`.

    Goes red if the `idle` rendering survives the subscription — an `idle` on a
    counter that can move is the same lie the `idle` was introduced to prevent,
    pointing the other way.
    """
    register_tools(store, projects_root)
    store.bump_anomaly(AnomalyKind.TOOL_PERMISSION_REFUSED.value)
    store.bump_anomaly(AnomalyKind.TOOL_PERMISSION_REFUSED.value)
    store.bump_anomaly(AnomalyKind.TOOL_BLOCKED_BY_HOOK.value)

    code = main(["doctor"], out=out, err=err, host=scripted_host(runtime_dir=tmp_path / "run"))

    assert code == EXIT_OK, err.getvalue()
    block = anomalies_block(out.getvalue())
    assert f"{AnomalyKind.TOOL_PERMISSION_REFUSED.value} 2" in block, block
    assert f"{AnomalyKind.TOOL_BLOCKED_BY_HOOK.value} 1" in block, block
    assert "idle" not in block, block
    assert "not subscribed" not in block, block
    # …and every counter that was always a count still reads as one.
    assert f"{AnomalyKind.MALFORMED_PAYLOAD.value} 0" in block, block


def test_the_idle_rendering_is_gone_not_merely_unused() -> None:
    """The structural half of the same claim: `cli/` holds no idle-list at all.

    Left in place but unreferenced, `IDLE_ANOMALIES` is a loaded gun — the next
    counter that looks permanently dead gets added to it, and the reason string
    still cites a blocker that is closed. Goes red if either survives, or is
    re-introduced without a reader noticing.
    """
    assert not hasattr(commands, "IDLE_ANOMALIES")
    assert not hasattr(commands, "IDLE_REASON")
