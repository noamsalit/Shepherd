"""T21 — the three `sdk-cli` counters, asserted at all **three** of their sites.

`sdk_cli_skipped` is the denominator and keeps its meaning: every `sdk-cli`
registry entry the sweep saw and did not register. `sdk_cli_reconciled` and
`sdk_cli_missed` are the two halves that stop it reading as coverage. A counter
added in two of its three sites is a counter that disagrees with itself, and
revision 1 of this task's plan listed only two of them — so the three names come
from **one** source of truth here (`DiscoveryStatus`, the producer) and every
site is checked against it rather than against a retyped list.

Seam: `main(argv)` → `invoke()`, the same seam as the rest of `tests/cli/`,
plus `project_discovery`, which is the projection `invoke()` renders from.
"""

from __future__ import annotations

import io
from pathlib import Path

from cli.conftest import register_tools, scripted_host

from shepherd.cli.commands import describe_discovery
from shepherd.cli.main import EXIT_OK, main
from shepherd.signals.discovery_loop import DISCOVERY_STATUS_KEY, DiscoveryStatus
from shepherd.store.db import Store
from shepherd.toolsurface.tools_m1 import project_discovery

#: Derived from the producer, never retyped: a name added to `DiscoveryStatus`
#: and forgotten at a rendering site fails here instead of shipping silent.
SDK_CLI_COUNTERS = tuple(
    name for name in DiscoveryStatus.__dataclass_fields__ if name.startswith("sdk_cli_")
)

PUBLISHED: dict[str, object] = {
    "hooks": "absent",
    "registry_sessions": 3,
    "sdk_cli_skipped": 7,
    "sdk_cli_reconciled": 5,
    "sdk_cli_missed": 2,
    "skipped_other": 4,
    "unknown_status": 1,
    "scan_interval_s": 2.0,
    "last_scan_at": "2026-09-16T10:00:30Z",
}


def test_the_producer_has_exactly_the_three_counters() -> None:
    """The case count this module's loops assert, so an empty loop cannot pass."""
    assert SDK_CLI_COUNTERS == ("sdk_cli_skipped", "sdk_cli_reconciled", "sdk_cli_missed")
    assert len(SDK_CLI_COUNTERS) == 3


def test_project_discovery_whitelists_all_three_counters() -> None:
    """`tools_m1.py`'s mapping — site two of three. Goes red if a counter is
    dropped from the whitelist, which silently degrades it to `0` (F16)."""
    projected = project_discovery(PUBLISHED)

    assert [projected[name] for name in SDK_CLI_COUNTERS] == [7, 5, 2]


def test_project_discovery_degrades_an_absent_counter_to_zero_not_to_a_crash() -> None:
    """The negative control for the whitelist: an older `app_state` blob written
    before this task shipped is still readable, and reads as the count it is."""
    older = {name: value for name, value in PUBLISHED.items() if name != "sdk_cli_missed"}

    projected = project_discovery(older)

    assert projected["sdk_cli_missed"] == 0
    assert projected["sdk_cli_reconciled"] == 5


def test_doctor_reports_all_three_counters(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Site three of three — `cli/commands.py`'s rendered line.

    Goes red if any of the three is hidden, **or** if this line disagrees with
    `tools_m1.py`'s mapping: the values asserted are the ones that travelled the
    whole way from `app_state` through the projection to the printed string.
    """
    register_tools(store, projects_root)
    store.set_app_state(DISCOVERY_STATUS_KEY, PUBLISHED)

    code = main(
        ["doctor"],
        out=out,
        err=err,
        host=scripted_host(runtime_dir=tmp_path / "run"),
    )

    assert code == EXIT_OK, err.getvalue()
    line = next(
        text for text in out.getvalue().splitlines() if text.startswith("discovery:")
    )
    # M1's wording for the denominator is preserved verbatim — `sdk_cli_skipped`
    # keeps its meaning, and `test_doctor_reports_skipped_and_unknown_counts`
    # still reads it.
    assert "7 skipped as non-interactive" in line, line
    assert "5 of those reconciled" in line, line
    assert "2 missed" in line, line
    # Arrival before absence: every counter's *number* is in the line, not just
    # its word — a label with no value would satisfy a substring check on names.
    for name in SDK_CLI_COUNTERS:
        assert str(PUBLISHED[name]) in line, (name, line)


def test_reconciled_is_never_rendered_without_missed() -> None:
    """Principle 5, made mechanical. `sdk_cli_reconciled` alone reads as coverage
    the reconcile has not earned — a `-p` run shorter than one sweep is never
    reconciled at all. Goes red if a later edit keeps the flattering counter and
    drops the honest one."""
    rendered = describe_discovery({"discovery": PUBLISHED})

    assert "reconciled" in rendered
    assert "missed" in rendered
    without_missed = describe_discovery(
        {"discovery": {k: v for k, v in PUBLISHED.items() if k != "sdk_cli_missed"}}
    )
    # Absent from the store is still rendered — as `0 missed`, which is what the
    # projection degrades an unknown to, and is visible rather than omitted.
    assert "missed" in without_missed
