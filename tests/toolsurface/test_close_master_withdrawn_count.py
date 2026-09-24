"""BC-30: controld's stop line counts every approval shutdown withdrew.

`close_master()` used to call `interrupt_master()` first, which withdraws the
master's own cards and discards the count, and only then run the counted sweep —
so a shutdown that freed the master's card reported `0`. Composed over
`tests/daemons/test_shutdown_master.py`'s world (the shipped
`compose_tool_surface`, a master parked on a real gated call).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.store.db import Store, open_store
from shepherd.toolsurface import client, compose
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.types import Audience, CallerContext

# `tests/` has no `__init__.py`: `test_shutdown_master` imports its sibling
# `scripted_hosts` by bare name, so its directory has to be importable too.
_DAEMONS_DIR = str(Path(__file__).resolve().parents[1] / "daemons")
if _DAEMONS_DIR not in sys.path:
    sys.path.insert(0, _DAEMONS_DIR)

from scripted_hosts import build_scripted_host  # noqa: E402
from test_shutdown_master import TIMEOUT_S, Composed, wait_for_cards  # noqa: E402


@pytest.fixture()
def composed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Composed]:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    store: Store = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield Composed(store, build_scripted_host(tmp_path), tmp_path)
    finally:
        compose.reset_master_plane()
        client.reset_master_client()
        store.close()


def test_close_master_counts_the_masters_own_card(composed: Composed) -> None:
    """One card, the master turn's own: shutdown freed one, so it says one."""
    invoke(
        "master_send",
        {"text": "go"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-1"),
    )
    assert composed.entered.wait(TIMEOUT_S), "the turn never reached its tool call"
    card = wait_for_cards(composed, 1)[0]
    assert card.turn_id == composed.master.turn_id

    assert compose.close_master(TIMEOUT_S) == 1
    assert composed.wiring.approvals.pending() == ()
